"""Vector Qdrant node - HTTP-backed vector store using the Qdrant REST API.

Same operation surface as :mod:`weftlyflow.nodes.ai.vector_memory`
and :mod:`weftlyflow.nodes.ai.vector_pgvector` so swapping backends
is a one-property change. Qdrant collections act as the table
equivalent; ``namespace`` is stored in the point payload and every
query / delete / clear filters on it so one collection can host many
partitions without clashes.

Distance metrics map onto Qdrant's three supported kinds:

* ``cosine``    -> ``Cosine`` (score is already higher-is-better).
* ``dot``       -> ``Dot``    (score is inner product, higher-is-better).
* ``euclidean`` -> ``Euclid`` (score is L2 distance; we negate so
  "higher = more similar" holds across backends).

The node speaks REST directly via ``httpx.AsyncClient``; Qdrant's
Python SDK is deliberately avoided to keep the transitive dependency
count down and to honor weftlyinfo.md §23 (no vendor
clients for surfaces we already have first-party plumbing for).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.qdrant_api import base_url_from
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
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.credentials.base import BaseCredentialType
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "qdrant_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.qdrant_api",)

OP_UPSERT: str = "upsert"
OP_QUERY: str = "query"
OP_DELETE: str = "delete"
OP_CLEAR: str = "clear"
OP_ENSURE_SCHEMA: str = "ensure_schema"

_SUPPORTED_OPERATIONS: frozenset[str] = frozenset(
    {OP_UPSERT, OP_QUERY, OP_DELETE, OP_CLEAR, OP_ENSURE_SCHEMA},
)

METRIC_COSINE: str = "cosine"
METRIC_DOT: str = "dot"
METRIC_EUCLIDEAN: str = "euclidean"

_SUPPORTED_METRICS: frozenset[str] = frozenset(
    {METRIC_COSINE, METRIC_DOT, METRIC_EUCLIDEAN},
)

_METRIC_TO_QDRANT: dict[str, str] = {
    METRIC_COSINE: "Cosine",
    METRIC_DOT: "Dot",
    METRIC_EUCLIDEAN: "Euclid",
}

_DEFAULT_COLLECTION: str = "weftlyflow_vectors"
_DEFAULT_NAMESPACE: str = "default"
_DEFAULT_TOP_K: int = 5
_DEFAULT_DIMENSIONS: int = 1536
_DEFAULT_METRIC: str = METRIC_COSINE
_NAMESPACE_PAYLOAD_KEY: str = "_weftlyflow_namespace"
_DEFAULT_TIMEOUT_SECONDS: float = 30.0

log = structlog.get_logger(__name__)


class VectorQdrantNode(BaseNode):
    """External vector store backed by the Qdrant REST API."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.vector_qdrant",
        version=1,
        display_name="Vector Qdrant",
        description=(
            "External vector store backed by Qdrant. Same upsert / "
            "query / delete / clear surface as vector_memory so the "
            "two are swappable."
        ),
        icon="icons/vector-qdrant.svg",
        category=NodeCategory.AI,
        group=["ai", "retrieval"],
        documentation_url="https://api.qdrant.tech/api-reference",
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
                name="collection",
                display_name="Collection",
                type="string",
                default=_DEFAULT_COLLECTION,
                description="Qdrant collection that hosts the vectors.",
            ),
            PropertySchema(
                name="namespace",
                display_name="Namespace",
                type="string",
                default=_DEFAULT_NAMESPACE,
                description=(
                    "Payload-scoped partition. Stored under "
                    f"'{_NAMESPACE_PAYLOAD_KEY}' and filtered on every "
                    "query / delete / clear."
                ),
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
                description=(
                    "Vector dimensionality used when creating the "
                    "collection."
                ),
                display_options=DisplayOptions(
                    show={"operation": [OP_ENSURE_SCHEMA]},
                ),
            ),
            PropertySchema(
                name="id",
                display_name="ID",
                type="string",
                description=(
                    "Point id for upsert or delete. Must be a valid "
                    "Qdrant id (unsigned int or UUID)."
                ),
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
                description=(
                    "Used by both 'ensure_schema' (collection config) "
                    "and 'query' (score normalisation)."
                ),
                display_options=DisplayOptions(
                    show={"operation": [OP_QUERY, OP_ENSURE_SCHEMA]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Dispatch each input item to the appropriate Qdrant operation."""
        cred_cls, cred_payload = await _resolve_credential(ctx)
        base_url = base_url_from(str(cred_payload.get("base_url") or ""))
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        seed = items or [Item()]
        emitted: list[Item] = []
        async with httpx.AsyncClient(
            base_url=base_url, timeout=_DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                emitted.append(
                    await _run_one(
                        ctx, client, cred_cls, cred_payload, item, bound,
                    ),
                )
        return [emitted]


async def _resolve_credential(
    ctx: ExecutionContext,
) -> tuple[BaseCredentialType, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Vector Qdrant: a qdrant_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return credential


async def _run_one(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    item: Item,
    bound: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_QUERY).strip()
    if operation not in _SUPPORTED_OPERATIONS:
        msg = f"Vector Qdrant: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    collection = str(params.get("collection") or _DEFAULT_COLLECTION).strip()

    if operation == OP_ENSURE_SCHEMA:
        return await _do_ensure_schema(
            ctx, client, cred_cls, cred_payload, params, collection, bound,
        )

    namespace = str(params.get("namespace") or _DEFAULT_NAMESPACE)
    if operation == OP_UPSERT:
        return await _do_upsert(
            ctx, client, cred_cls, cred_payload,
            params, collection, namespace, bound,
        )
    if operation == OP_QUERY:
        return await _do_query(
            ctx, client, cred_cls, cred_payload,
            params, collection, namespace, bound,
        )
    if operation == OP_DELETE:
        return await _do_delete(
            ctx, client, cred_cls, cred_payload,
            params, collection, namespace, bound,
        )
    return await _do_clear(
        ctx, client, cred_cls, cred_payload,
        collection, namespace, bound,
    )


async def _do_ensure_schema(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    params: dict[str, Any],
    collection: str,
    bound: Any,
) -> Item:
    dimensions = _coerce_positive_int(
        params.get("dimensions"), ctx, field="dimensions",
        default=_DEFAULT_DIMENSIONS,
    )
    metric = _coerce_metric(params.get("metric") or _DEFAULT_METRIC, ctx)
    existed = await _collection_exists(
        client, cred_cls, cred_payload, collection, ctx, bound,
    )
    if not existed:
        body = {
            "vectors": {
                "size": dimensions,
                "distance": _METRIC_TO_QDRANT[metric],
            },
        }
        await _request(
            client, cred_cls, cred_payload,
            method="PUT",
            path=f"/collections/{collection}",
            json=body,
            ctx=ctx,
            bound=bound,
        )
    return Item(
        json={
            "operation": OP_ENSURE_SCHEMA,
            "collection": collection,
            "dimensions": dimensions,
            "metric": metric,
            "created": not existed,
        },
    )


async def _do_upsert(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    params: dict[str, Any],
    collection: str,
    namespace: str,
    bound: Any,
) -> Item:
    record_id = _coerce_id(params.get("id"), ctx)
    vector = _coerce_vector(params.get("vector"), ctx)
    payload = _coerce_payload(params.get("payload"), ctx)
    payload[_NAMESPACE_PAYLOAD_KEY] = namespace
    body = {
        "points": [
            {"id": record_id, "vector": vector, "payload": payload},
        ],
    }
    await _request(
        client, cred_cls, cred_payload,
        method="PUT",
        path=f"/collections/{collection}/points",
        params={"wait": "true"},
        json=body,
        ctx=ctx,
        bound=bound,
    )
    return Item(
        json={
            "operation": OP_UPSERT,
            "collection": collection,
            "namespace": namespace,
            "id": record_id,
            "dimensions": len(vector),
        },
    )


async def _do_query(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    params: dict[str, Any],
    collection: str,
    namespace: str,
    bound: Any,
) -> Item:
    vector = _coerce_vector(params.get("vector"), ctx)
    top_k = _coerce_positive_int(
        params.get("top_k"), ctx, field="top_k", default=_DEFAULT_TOP_K,
    )
    metric = _coerce_metric(params.get("metric") or _DEFAULT_METRIC, ctx)
    body = {
        "vector": vector,
        "limit": top_k,
        "with_payload": True,
        "filter": _namespace_filter(namespace),
    }
    response = await _request(
        client, cred_cls, cred_payload,
        method="POST",
        path=f"/collections/{collection}/points/search",
        json=body,
        ctx=ctx,
        bound=bound,
    )
    matches = _parse_matches(response, metric)
    return Item(
        json={
            "operation": OP_QUERY,
            "collection": collection,
            "namespace": namespace,
            "matches": matches,
            "count": len(matches),
        },
    )


async def _do_delete(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    params: dict[str, Any],
    collection: str,
    namespace: str,
    bound: Any,
) -> Item:
    record_id = _coerce_id(params.get("id"), ctx)
    # Scope delete to (id, namespace): a malicious or accidental id
    # collision from another namespace must not take out an unrelated
    # point.
    body = {
        "filter": {
            "must": [
                {"has_id": [record_id]},
                _namespace_match(namespace),
            ],
        },
    }
    await _request(
        client, cred_cls, cred_payload,
        method="POST",
        path=f"/collections/{collection}/points/delete",
        params={"wait": "true"},
        json=body,
        ctx=ctx,
        bound=bound,
    )
    return Item(
        json={
            "operation": OP_DELETE,
            "collection": collection,
            "namespace": namespace,
            "id": record_id,
        },
    )


async def _do_clear(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    collection: str,
    namespace: str,
    bound: Any,
) -> Item:
    body = {"filter": _namespace_filter(namespace)}
    await _request(
        client, cred_cls, cred_payload,
        method="POST",
        path=f"/collections/{collection}/points/delete",
        params={"wait": "true"},
        json=body,
        ctx=ctx,
        bound=bound,
    )
    return Item(
        json={
            "operation": OP_CLEAR,
            "collection": collection,
            "namespace": namespace,
        },
    )


async def _collection_exists(
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    collection: str,
    ctx: ExecutionContext,
    bound: Any,
) -> bool:
    request = client.build_request("GET", f"/collections/{collection}")
    await cred_cls.inject(cred_payload, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        bound.error("vector_qdrant.request_failed", error=str(exc))
        msg = f"Vector Qdrant: network error: {exc}"
        raise NodeExecutionError(
            msg, node_id=ctx.node.id, original=exc,
        ) from exc
    if response.status_code == httpx.codes.NOT_FOUND:
        return False
    if response.status_code >= httpx.codes.BAD_REQUEST:
        _raise_for_status(response, ctx, bound)
    return True


async def _request(
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    method: str,
    path: str,
    ctx: ExecutionContext,
    bound: Any,
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = client.build_request(
        method, path, params=params, json=json,
    )
    await cred_cls.inject(cred_payload, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        bound.error("vector_qdrant.request_failed", error=str(exc))
        msg = f"Vector Qdrant: network error: {exc}"
        raise NodeExecutionError(
            msg, node_id=ctx.node.id, original=exc,
        ) from exc
    if response.status_code >= httpx.codes.BAD_REQUEST:
        _raise_for_status(response, ctx, bound)
    return _safe_json(response)


def _raise_for_status(
    response: httpx.Response, ctx: ExecutionContext, bound: Any,
) -> None:
    payload = _safe_json(response)
    error = _error_message(payload, response.status_code)
    bound.warning(
        "vector_qdrant.api_error",
        status=response.status_code,
        error=error,
    )
    msg = f"Vector Qdrant failed (HTTP {response.status_code}): {error}"
    raise NodeExecutionError(msg, node_id=ctx.node.id)


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    if not response.content:
        return {}
    try:
        parsed = response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}
    return parsed if isinstance(parsed, dict) else {"result": parsed}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        status = payload.get("status")
        if isinstance(status, dict):
            error = status.get("error")
            if isinstance(error, str) and error:
                return error
        if isinstance(status, str) and status:
            return status
    return f"HTTP {status_code}"


def _parse_matches(payload: dict[str, Any], metric: str) -> list[dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in result:
        if not isinstance(entry, dict):
            continue
        score = entry.get("score")
        if not isinstance(score, (int, float)):
            continue
        normalized = _score_from_qdrant(metric, float(score))
        payload_field = entry.get("payload")
        payload_copy = (
            dict(payload_field) if isinstance(payload_field, dict) else {}
        )
        # The namespace marker is an internal detail — hide it from callers.
        payload_copy.pop(_NAMESPACE_PAYLOAD_KEY, None)
        out.append(
            {
                "id": entry.get("id"),
                "payload": payload_copy,
                "score": normalized,
            },
        )
    return out


def _score_from_qdrant(metric: str, raw: float) -> float:
    # Qdrant returns the distance for Euclid and the raw similarity for
    # Cosine and Dot. Normalising here keeps callers metric-agnostic.
    if metric == METRIC_EUCLIDEAN:
        return -raw
    return raw


def _namespace_filter(namespace: str) -> dict[str, Any]:
    return {"must": [_namespace_match(namespace)]}


def _namespace_match(namespace: str) -> dict[str, Any]:
    return {"key": _NAMESPACE_PAYLOAD_KEY, "match": {"value": namespace}}


def _coerce_id(raw: Any, ctx: ExecutionContext) -> str | int:
    if isinstance(raw, bool):  # bool is a subclass of int — reject early.
        msg = "Vector Qdrant: 'id' must be a string or integer"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if isinstance(raw, int):
        if raw < 0:
            msg = "Vector Qdrant: integer 'id' must be non-negative"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        return raw
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    msg = "Vector Qdrant: 'id' is required"
    raise NodeExecutionError(msg, node_id=ctx.node.id)


def _coerce_vector(raw: Any, ctx: ExecutionContext) -> list[float]:
    if not isinstance(raw, list) or not raw:
        msg = "Vector Qdrant: 'vector' must be a non-empty JSON array of numbers"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    out: list[float] = []
    for entry in raw:
        if isinstance(entry, bool) or not isinstance(entry, (int, float)):
            msg = "Vector Qdrant: every 'vector' element must be a number"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        out.append(float(entry))
    return out


def _coerce_payload(raw: Any, ctx: ExecutionContext) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        msg = "Vector Qdrant: 'payload' must be a JSON object"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return dict(raw)


def _coerce_metric(raw: Any, ctx: ExecutionContext) -> str:
    metric = str(raw or _DEFAULT_METRIC)
    if metric not in _SUPPORTED_METRICS:
        msg = f"Vector Qdrant: unsupported metric {metric!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return metric


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
            f"Vector Qdrant: {field!r} must be an integer",
            node_id=ctx.node.id,
            original=exc,
        ) from exc
    if value < 1:
        msg = f"Vector Qdrant: {field!r} must be >= 1"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return value
