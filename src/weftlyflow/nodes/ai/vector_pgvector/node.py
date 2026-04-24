"""Vector Pgvector node - persistent vector store backed by pgvector.

Same operation surface as :mod:`weftlyflow.nodes.ai.vector_memory`
(upsert / query / delete / clear) so switching between the two
backends is a one-property change on the node. Adds ``ensure_schema``
so workflows can idempotently provision the table + index on first
run without an external migration step.

One psycopg3 async connection is opened per ``execute`` call and
reused across every input item - fan-out inside a workflow should
stay cheap even for hundreds of upserts. Connection management is
factored through the module-level :func:`_open_connection` hook so
unit tests can substitute a fake connection without touching a real
Postgres.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import psycopg
import structlog

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    DisplayOptions,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.ai.vector_pgvector.sql import (
    METRIC_COSINE,
    METRIC_DOT,
    METRIC_EUCLIDEAN,
    SUPPORTED_METRICS,
    build_clear,
    build_delete,
    build_ensure_schema,
    build_query,
    build_upsert,
    score_from_distance,
    validate_identifier,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "postgres_dsn"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.postgres_dsn",)

OP_UPSERT: str = "upsert"
OP_QUERY: str = "query"
OP_DELETE: str = "delete"
OP_CLEAR: str = "clear"
OP_ENSURE_SCHEMA: str = "ensure_schema"

_SUPPORTED_OPERATIONS: frozenset[str] = frozenset(
    {OP_UPSERT, OP_QUERY, OP_DELETE, OP_CLEAR, OP_ENSURE_SCHEMA},
)

_DEFAULT_TABLE: str = "weftlyflow_vectors"
_DEFAULT_NAMESPACE: str = "default"
_DEFAULT_TOP_K: int = 5
_DEFAULT_DIMENSIONS: int = 1536

log = structlog.get_logger(__name__)


async def _open_connection(dsn: str) -> psycopg.AsyncConnection[Any]:
    """Open an async psycopg connection.

    Isolated behind a module-level hook so tests can monkey-patch the
    return value with a fake connection without reaching for a real
    Postgres instance.
    """
    return await psycopg.AsyncConnection.connect(dsn)


class VectorPgvectorNode(BaseNode):
    """Persistent vector store backed by pgvector on Postgres."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.vector_pgvector",
        version=1,
        display_name="Vector Pgvector",
        description=(
            "Persistent vector store backed by pgvector. Mirrors the "
            "vector_memory operation surface so the two are swappable."
        ),
        icon="icons/vector-pgvector.svg",
        category=NodeCategory.AI,
        group=["ai", "retrieval"],
        documentation_url="https://github.com/pgvector/pgvector",
        credentials=[
            CredentialSlot(
                name=_CREDENTIAL_SLOT,
                required=True,
                credential_types=list(_CREDENTIAL_SLUGS),
            ),
        ],
        properties=[
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=OP_QUERY,
                required=True,
                options=[
                    PropertyOption(value=OP_UPSERT, label="Upsert"),
                    PropertyOption(value=OP_QUERY, label="Query"),
                    PropertyOption(value=OP_DELETE, label="Delete"),
                    PropertyOption(value=OP_CLEAR, label="Clear"),
                    PropertyOption(
                        value=OP_ENSURE_SCHEMA, label="Ensure Schema",
                    ),
                ],
            ),
            PropertySchema(
                name="table",
                display_name="Table",
                type="string",
                default=_DEFAULT_TABLE,
                description=(
                    "Target table. Must match "
                    "^[A-Za-z_][A-Za-z0-9_]*$ (case preserved)."
                ),
            ),
            PropertySchema(
                name="namespace",
                display_name="Namespace",
                type="string",
                default=_DEFAULT_NAMESPACE,
                description="Collection-like partition stored in a column.",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_UPSERT, OP_QUERY, OP_DELETE, OP_CLEAR,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="dimensions",
                display_name="Dimensions",
                type="number",
                default=_DEFAULT_DIMENSIONS,
                description="Vector dimensionality when creating the table.",
                display_options=DisplayOptions(
                    show={"operation": [OP_ENSURE_SCHEMA]},
                ),
            ),
            PropertySchema(
                name="id",
                display_name="ID",
                type="string",
                description="Record id for upsert or delete.",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPSERT, OP_DELETE]},
                ),
            ),
            PropertySchema(
                name="vector",
                display_name="Vector",
                type="json",
                description="JSON array of floats.",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPSERT, OP_QUERY]},
                ),
            ),
            PropertySchema(
                name="payload",
                display_name="Payload",
                type="json",
                description="JSON object stored alongside the vector.",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPSERT]},
                ),
            ),
            PropertySchema(
                name="top_k",
                display_name="Top K",
                type="number",
                default=_DEFAULT_TOP_K,
                display_options=DisplayOptions(
                    show={"operation": [OP_QUERY]},
                ),
            ),
            PropertySchema(
                name="metric",
                display_name="Metric",
                type="options",
                default=METRIC_COSINE,
                options=[
                    PropertyOption(value=METRIC_COSINE, label="Cosine"),
                    PropertyOption(value=METRIC_DOT, label="Dot product"),
                    PropertyOption(value=METRIC_EUCLIDEAN, label="Euclidean"),
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_QUERY]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Dispatch each input item to the appropriate pgvector operation."""
        dsn = await _resolve_dsn(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        try:
            conn = await _open_connection(dsn)
        except psycopg.Error as exc:
            bound.error("vector_pgvector.connect_failed", error=str(exc))
            msg = f"Vector Pgvector: connection failed: {exc}"
            raise NodeExecutionError(
                msg, node_id=ctx.node.id, original=exc,
            ) from exc
        try:
            emitted: list[Item] = []
            async with conn:
                for item in seed:
                    emitted.append(await _run_one(ctx, conn, item))
        except psycopg.Error as exc:
            bound.error("vector_pgvector.operation_failed", error=str(exc))
            msg = f"Vector Pgvector: database error: {exc}"
            raise NodeExecutionError(
                msg, node_id=ctx.node.id, original=exc,
            ) from exc
        return [emitted]


async def _resolve_dsn(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Vector Pgvector: a postgres_dsn credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    dsn = str(payload.get("dsn") or "").strip()
    if not dsn:
        msg = "Vector Pgvector: credential has an empty 'dsn'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return dsn


async def _run_one(
    ctx: ExecutionContext,
    conn: psycopg.AsyncConnection[Any],
    item: Item,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_QUERY).strip()
    if operation not in _SUPPORTED_OPERATIONS:
        msg = f"Vector Pgvector: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    table = _coerce_identifier(
        params.get("table") or _DEFAULT_TABLE, ctx, field="table",
    )

    if operation == OP_ENSURE_SCHEMA:
        return await _do_ensure_schema(ctx, conn, params, table)

    namespace = str(params.get("namespace") or _DEFAULT_NAMESPACE)
    if operation == OP_UPSERT:
        return await _do_upsert(ctx, conn, params, table, namespace)
    if operation == OP_QUERY:
        return await _do_query(ctx, conn, params, table, namespace)
    if operation == OP_DELETE:
        return await _do_delete(ctx, conn, params, table, namespace)
    return await _do_clear(conn, table, namespace)


async def _do_ensure_schema(
    ctx: ExecutionContext,
    conn: psycopg.AsyncConnection[Any],
    params: dict[str, Any],
    table: str,
) -> Item:
    dimensions = _coerce_positive_int(
        params.get("dimensions"), ctx, field="dimensions",
        default=_DEFAULT_DIMENSIONS,
    )
    try:
        statements = build_ensure_schema(
            table=table, dimensions=dimensions,
        )
    except ValueError as exc:
        raise NodeExecutionError(
            f"Vector Pgvector: {exc}", node_id=ctx.node.id, original=exc,
        ) from exc
    async with conn.cursor() as cur:
        for statement, sql_params in statements:
            await cur.execute(statement, sql_params)
    return Item(
        json={
            "operation": OP_ENSURE_SCHEMA,
            "table": table,
            "dimensions": dimensions,
        },
    )


async def _do_upsert(
    ctx: ExecutionContext,
    conn: psycopg.AsyncConnection[Any],
    params: dict[str, Any],
    table: str,
    namespace: str,
) -> Item:
    record_id = str(params.get("id") or "").strip()
    if not record_id:
        msg = "Vector Pgvector: 'id' is required for upsert"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    vector = _coerce_vector(params.get("vector"), ctx)
    payload = _coerce_payload(params.get("payload"), ctx)
    statement, sql_params = build_upsert(
        table=table,
        namespace=namespace,
        record_id=record_id,
        vector=vector,
        payload=payload,
    )
    async with conn.cursor() as cur:
        await cur.execute(statement, sql_params)
    return Item(
        json={
            "operation": OP_UPSERT,
            "table": table,
            "namespace": namespace,
            "id": record_id,
            "dimensions": len(vector),
        },
    )


async def _do_query(
    ctx: ExecutionContext,
    conn: psycopg.AsyncConnection[Any],
    params: dict[str, Any],
    table: str,
    namespace: str,
) -> Item:
    vector = _coerce_vector(params.get("vector"), ctx)
    top_k = _coerce_positive_int(
        params.get("top_k"), ctx, field="top_k", default=_DEFAULT_TOP_K,
    )
    metric = str(params.get("metric") or METRIC_COSINE)
    if metric not in SUPPORTED_METRICS:
        msg = f"Vector Pgvector: unsupported metric {metric!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    statement, sql_params = build_query(
        table=table,
        namespace=namespace,
        vector=vector,
        top_k=top_k,
        metric=metric,
    )
    async with conn.cursor() as cur:
        await cur.execute(statement, sql_params)
        rows = await cur.fetchall()
    matches = [_row_to_match(row, metric) for row in rows]
    return Item(
        json={
            "operation": OP_QUERY,
            "table": table,
            "namespace": namespace,
            "matches": matches,
            "count": len(matches),
        },
    )


async def _do_delete(
    ctx: ExecutionContext,
    conn: psycopg.AsyncConnection[Any],
    params: dict[str, Any],
    table: str,
    namespace: str,
) -> Item:
    record_id = str(params.get("id") or "").strip()
    if not record_id:
        msg = "Vector Pgvector: 'id' is required for delete"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    statement, sql_params = build_delete(
        table=table, namespace=namespace, record_id=record_id,
    )
    async with conn.cursor() as cur:
        await cur.execute(statement, sql_params)
        deleted = (cur.rowcount or 0) > 0
    return Item(
        json={
            "operation": OP_DELETE,
            "table": table,
            "namespace": namespace,
            "id": record_id,
            "deleted": deleted,
        },
    )


async def _do_clear(
    conn: psycopg.AsyncConnection[Any],
    table: str,
    namespace: str,
) -> Item:
    statement, sql_params = build_clear(table=table, namespace=namespace)
    async with conn.cursor() as cur:
        await cur.execute(statement, sql_params)
        cleared = cur.rowcount or 0
    return Item(
        json={
            "operation": OP_CLEAR,
            "table": table,
            "namespace": namespace,
            "cleared": cleared,
        },
    )


def _row_to_match(row: Any, metric: str) -> dict[str, Any]:
    record_id, payload, distance = row
    return {
        "id": record_id,
        "payload": dict(payload) if isinstance(payload, dict) else {},
        "score": score_from_distance(metric, float(distance)),
    }


def _coerce_identifier(raw: Any, ctx: ExecutionContext, *, field: str) -> str:
    name = str(raw or "").strip()
    if not name:
        msg = f"Vector Pgvector: {field!r} is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        validate_identifier(name, field=field)
    except ValueError as exc:
        raise NodeExecutionError(
            f"Vector Pgvector: {exc}", node_id=ctx.node.id, original=exc,
        ) from exc
    return name


def _coerce_vector(raw: Any, ctx: ExecutionContext) -> list[float]:
    if not isinstance(raw, list) or not raw:
        msg = "Vector Pgvector: 'vector' must be a non-empty JSON array of numbers"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    out: list[float] = []
    for entry in raw:
        if isinstance(entry, bool) or not isinstance(entry, (int, float)):
            msg = "Vector Pgvector: every 'vector' element must be a number"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        out.append(float(entry))
    return out


def _coerce_payload(raw: Any, ctx: ExecutionContext) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        msg = "Vector Pgvector: 'payload' must be a JSON object"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return dict(raw)


def _coerce_positive_int(
    raw: Any,
    ctx: ExecutionContext,
    *,
    field: str,
    default: int,
) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise NodeExecutionError(
            f"Vector Pgvector: {field!r} must be an integer",
            node_id=ctx.node.id,
            original=exc,
        ) from exc
    if value < 1:
        msg = f"Vector Pgvector: {field!r} must be >= 1"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return value
