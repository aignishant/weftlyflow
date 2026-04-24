"""Vector Memory node - in-process vector store for RAG workflows.

Pairs with ``text_splitter`` and the OpenAI ``create_embedding``
operation to provide a complete zero-infra retrieval loop:

1. ``text_splitter`` chunks a document.
2. An OpenAI embedding call maps each chunk to a vector.
3. ``vector_memory`` (``upsert``) indexes the chunk.
4. A query-time embedding fed to ``vector_memory`` (``query``)
   returns the top-k chunks with a similarity score.

State lives in :data:`ctx.static_data` under
:data:`~weftlyflow.nodes.ai.vector_memory.store.VECTOR_NAMESPACE` and
is partitioned by ``namespace`` so one workflow can run multiple
collections without clashes.

Operations:

* ``upsert`` - insert or replace ``id`` with ``vector`` + ``payload``.
* ``query`` - return the top-``top_k`` records most similar to
  ``vector`` under the chosen ``metric`` (cosine/dot/euclidean).
* ``delete`` - remove a record by ``id``.
* ``clear`` - drop every record in the namespace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    DisplayOptions,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.ai.vector_memory.store import (
    METRIC_COSINE,
    METRIC_DOT,
    METRIC_EUCLIDEAN,
    clear,
    delete,
    query,
    upsert,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

OP_UPSERT: str = "upsert"
OP_QUERY: str = "query"
OP_DELETE: str = "delete"
OP_CLEAR: str = "clear"

_SUPPORTED_OPERATIONS: frozenset[str] = frozenset(
    {OP_UPSERT, OP_QUERY, OP_DELETE, OP_CLEAR},
)
_DEFAULT_NAMESPACE: str = "default"
_DEFAULT_TOP_K: int = 5


class VectorMemoryNode(BaseNode):
    """In-process vector store with upsert / query / delete / clear."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.vector_memory",
        version=1,
        display_name="Vector Memory",
        description=(
            "Self-contained in-process vector store. Pairs with "
            "text_splitter + an embedding node for zero-infra RAG."
        ),
        icon="icons/vector-memory.svg",
        category=NodeCategory.AI,
        group=["ai", "retrieval"],
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
                ],
            ),
            PropertySchema(
                name="namespace",
                display_name="Namespace",
                type="string",
                default=_DEFAULT_NAMESPACE,
                description="Collection-like partition for this store.",
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
                display_options=DisplayOptions(show={"operation": [OP_UPSERT]}),
            ),
            PropertySchema(
                name="top_k",
                display_name="Top K",
                type="number",
                default=_DEFAULT_TOP_K,
                display_options=DisplayOptions(show={"operation": [OP_QUERY]}),
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
                display_options=DisplayOptions(show={"operation": [OP_QUERY]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Dispatch one store operation per input item."""
        seed = items or [Item()]
        return [[_run_one(ctx, item) for item in seed]]


def _run_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_QUERY).strip()
    if operation not in _SUPPORTED_OPERATIONS:
        msg = f"Vector Memory: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    namespace = str(params.get("namespace") or _DEFAULT_NAMESPACE)

    if operation == OP_UPSERT:
        return _do_upsert(ctx, params, namespace)
    if operation == OP_QUERY:
        return _do_query(ctx, params, namespace)
    if operation == OP_DELETE:
        return _do_delete(ctx, params, namespace)
    return _do_clear(ctx, namespace)


def _do_upsert(
    ctx: ExecutionContext, params: dict[str, Any], namespace: str,
) -> Item:
    record_id = str(params.get("id") or "").strip()
    if not record_id:
        msg = "Vector Memory: 'id' is required for upsert"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    vector = _coerce_vector(params.get("vector"), ctx)
    payload = _coerce_payload(params.get("payload"), ctx)
    stored = upsert(ctx.static_data, namespace, record_id, vector, payload)
    return Item(
        json={
            "operation": OP_UPSERT,
            "namespace": namespace,
            "id": stored["id"],
            "dimensions": len(stored["vector"]),
        },
    )


def _do_query(
    ctx: ExecutionContext, params: dict[str, Any], namespace: str,
) -> Item:
    vector = _coerce_vector(params.get("vector"), ctx)
    top_k = _coerce_top_k(params.get("top_k"), ctx)
    metric = str(params.get("metric") or METRIC_COSINE)
    try:
        matches = query(
            ctx.static_data,
            namespace,
            vector,
            top_k=top_k,
            metric=metric,
        )
    except ValueError as exc:
        raise NodeExecutionError(
            f"Vector Memory: {exc}", node_id=ctx.node.id, original=exc,
        ) from exc
    return Item(
        json={
            "operation": OP_QUERY,
            "namespace": namespace,
            "matches": matches,
            "count": len(matches),
        },
    )


def _do_delete(
    ctx: ExecutionContext, params: dict[str, Any], namespace: str,
) -> Item:
    record_id = str(params.get("id") or "").strip()
    if not record_id:
        msg = "Vector Memory: 'id' is required for delete"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    removed = delete(ctx.static_data, namespace, record_id)
    return Item(
        json={
            "operation": OP_DELETE,
            "namespace": namespace,
            "id": record_id,
            "deleted": removed,
        },
    )


def _do_clear(ctx: ExecutionContext, namespace: str) -> Item:
    count = clear(ctx.static_data, namespace)
    return Item(
        json={
            "operation": OP_CLEAR,
            "namespace": namespace,
            "cleared": count,
        },
    )


def _coerce_vector(raw: Any, ctx: ExecutionContext) -> list[float]:
    if not isinstance(raw, list) or not raw:
        msg = "Vector Memory: 'vector' must be a non-empty JSON array of numbers"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    out: list[float] = []
    for entry in raw:
        if isinstance(entry, bool) or not isinstance(entry, (int, float)):
            msg = "Vector Memory: every 'vector' element must be a number"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        out.append(float(entry))
    return out


def _coerce_payload(raw: Any, ctx: ExecutionContext) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        msg = "Vector Memory: 'payload' must be a JSON object"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return dict(raw)


def _coerce_top_k(raw: Any, ctx: ExecutionContext) -> int:
    if raw is None or raw == "":
        return _DEFAULT_TOP_K
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise NodeExecutionError(
            "Vector Memory: 'top_k' must be an integer",
            node_id=ctx.node.id,
            original=exc,
        ) from exc
    if value <= 0:
        msg = "Vector Memory: 'top_k' must be > 0"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return value
