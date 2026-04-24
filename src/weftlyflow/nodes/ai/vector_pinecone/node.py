"""Vector Pinecone node - managed vector store via Pinecone REST.

Same operation surface as :mod:`weftlyflow.nodes.ai.vector_memory`,
:mod:`weftlyflow.nodes.ai.vector_pgvector`, and
:mod:`weftlyflow.nodes.ai.vector_qdrant` so swapping backends is a
one-property change. Pinecone is the backend in the family whose
control and data planes live on *different* hosts:

* Control plane (``https://api.pinecone.io``) - ``ensure_schema``
  creates the index here and the node calls ``GET /indexes/{name}``
  to resolve the data-plane host when the user did not supply one.
* Data plane - a per-index host like
  ``my-index-proj.svc.us-east-1-aws.pinecone.io`` that hosts
  ``upsert`` / ``query`` / ``delete`` traffic. Cached per
  ``execute`` call so repeated items share one control-plane lookup.

Metric mapping:

* ``cosine``    -> ``cosine``     (similarity, higher is better).
* ``dot``       -> ``dotproduct`` (inner product, higher is better).
* ``euclidean`` -> ``euclidean``  (squared L2 distance; negated so
  "higher is better" holds uniformly across backends).

``ensure_schema`` creates a serverless index. ``cloud`` / ``region``
default to ``aws`` / ``us-east-1`` which works out of the box on the
Pinecone free tier; override them for pod-based deployments via a
prior manual ``POST /indexes`` and then use ``ensure_schema`` for
idempotent detection only.

Auth is a flat ``Api-Key: <key>`` header handled by
:class:`~weftlyflow.credentials.types.pinecone_api.PineconeApiCredential`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
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
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.credentials.base import BaseCredentialType
    from weftlyflow.engine.context import ExecutionContext


_CREDENTIAL_SLOT: str = "pinecone_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.pinecone_api",)

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

_METRIC_TO_PINECONE: dict[str, str] = {
    METRIC_COSINE: "cosine",
    METRIC_DOT: "dotproduct",
    METRIC_EUCLIDEAN: "euclidean",
}

_CONTROL_PLANE_HOST: str = "https://api.pinecone.io"
_DEFAULT_INDEX: str = "weftlyflow-vectors"
_DEFAULT_NAMESPACE: str = "default"
_DEFAULT_TOP_K: int = 5
_DEFAULT_DIMENSIONS: int = 1536
_DEFAULT_METRIC: str = METRIC_COSINE
_DEFAULT_CLOUD: str = "aws"
_DEFAULT_REGION: str = "us-east-1"
_DEFAULT_TIMEOUT_SECONDS: float = 30.0

log = structlog.get_logger(__name__)


class VectorPineconeNode(BaseNode):
    """Managed vector store backed by the Pinecone REST API."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.vector_pinecone",
        version=1,
        display_name="Vector Pinecone",
        description=(
            "Managed vector store backed by Pinecone. Same upsert / "
            "query / delete / clear surface as vector_memory so the "
            "backends are swappable."
        ),
        icon="icons/vector-pinecone.svg",
        category=NodeCategory.AI,
        group=["ai", "retrieval"],
        documentation_url="https://docs.pinecone.io/reference/api/introduction",
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
                name="index_name",
                display_name="Index Name",
                type="string",
                default=_DEFAULT_INDEX,
                description="Pinecone index that hosts the vectors.",
            ),
            PropertySchema(
                name="host",
                display_name="Data-Plane Host",
                type="string",
                description=(
                    "Per-index data-plane host (e.g. "
                    "'my-index-proj.svc.us-east-1-aws.pinecone.io'). "
                    "Leave blank to resolve via the control plane on "
                    "first use."
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
                name="namespace",
                display_name="Namespace",
                type="string",
                default=_DEFAULT_NAMESPACE,
                description=(
                    "Native Pinecone namespace. Applied to every "
                    "upsert / query / delete / clear to partition the "
                    "index."
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
                    "Vector dimensionality used when creating the index."
                ),
                display_options=DisplayOptions(
                    show={"operation": [OP_ENSURE_SCHEMA]},
                ),
            ),
            PropertySchema(
                name="cloud",
                display_name="Cloud",
                type="string",
                default=_DEFAULT_CLOUD,
                description="Serverless cloud ('aws', 'gcp', or 'azure').",
                display_options=DisplayOptions(
                    show={"operation": [OP_ENSURE_SCHEMA]},
                ),
            ),
            PropertySchema(
                name="region",
                display_name="Region",
                type="string",
                default=_DEFAULT_REGION,
                description="Serverless region (cloud-specific).",
                display_options=DisplayOptions(
                    show={"operation": [OP_ENSURE_SCHEMA]},
                ),
            ),
            PropertySchema(
                name="id",
                display_name="ID",
                type="string",
                description="Vector id for upsert or delete.",
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
                name="metadata",
                display_name="Metadata",
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
                    "Used by both 'ensure_schema' (index metric) and "
                    "'query' (score normalisation)."
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
        """Dispatch each input item to the appropriate Pinecone operation."""
        cred_cls, cred_payload = await _resolve_credential(ctx)
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        seed = items or [Item()]
        emitted: list[Item] = []
        host_cache: dict[str, str] = {}
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                emitted.append(
                    await _run_one(
                        ctx, client, cred_cls, cred_payload,
                        item, host_cache, bound,
                    ),
                )
        return [emitted]


async def _resolve_credential(
    ctx: ExecutionContext,
) -> tuple[BaseCredentialType, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Vector Pinecone: a pinecone_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return credential


async def _run_one(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    item: Item,
    host_cache: dict[str, str],
    bound: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_QUERY).strip()
    if operation not in _SUPPORTED_OPERATIONS:
        msg = f"Vector Pinecone: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    index_name = str(params.get("index_name") or _DEFAULT_INDEX).strip()
    if not index_name:
        msg = "Vector Pinecone: 'index_name' is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    if operation == OP_ENSURE_SCHEMA:
        return await _do_ensure_schema(
            ctx, client, cred_cls, cred_payload, params, index_name, bound,
        )

    host = await _resolve_host(
        ctx, client, cred_cls, cred_payload,
        index_name=index_name,
        explicit_host=str(params.get("host") or "").strip(),
        host_cache=host_cache,
        bound=bound,
    )
    namespace = str(params.get("namespace") or _DEFAULT_NAMESPACE)
    if operation == OP_UPSERT:
        return await _do_upsert(
            ctx, client, cred_cls, cred_payload,
            params, index_name, host, namespace, bound,
        )
    if operation == OP_QUERY:
        return await _do_query(
            ctx, client, cred_cls, cred_payload,
            params, index_name, host, namespace, bound,
        )
    if operation == OP_DELETE:
        return await _do_delete(
            ctx, client, cred_cls, cred_payload,
            params, index_name, host, namespace, bound,
        )
    return await _do_clear(
        ctx, client, cred_cls, cred_payload,
        index_name, host, namespace, bound,
    )


async def _do_ensure_schema(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    params: dict[str, Any],
    index_name: str,
    bound: Any,
) -> Item:
    dimensions = _coerce_positive_int(
        params.get("dimensions"), ctx, field="dimensions",
        default=_DEFAULT_DIMENSIONS,
    )
    metric = _coerce_metric(params.get("metric") or _DEFAULT_METRIC, ctx)
    cloud = str(params.get("cloud") or _DEFAULT_CLOUD).strip() or _DEFAULT_CLOUD
    region = (
        str(params.get("region") or _DEFAULT_REGION).strip()
        or _DEFAULT_REGION
    )
    existed = await _index_exists(
        client, cred_cls, cred_payload, index_name, ctx, bound,
    )
    if not existed:
        body = {
            "name": index_name,
            "dimension": dimensions,
            "metric": _METRIC_TO_PINECONE[metric],
            "spec": {"serverless": {"cloud": cloud, "region": region}},
        }
        await _request(
            client, cred_cls, cred_payload,
            method="POST",
            url=f"{_CONTROL_PLANE_HOST}/indexes",
            json_body=body,
            ctx=ctx,
            bound=bound,
        )
    return Item(
        json={
            "operation": OP_ENSURE_SCHEMA,
            "index_name": index_name,
            "dimensions": dimensions,
            "metric": metric,
            "cloud": cloud,
            "region": region,
            "created": not existed,
        },
    )


async def _do_upsert(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    params: dict[str, Any],
    index_name: str,
    host: str,
    namespace: str,
    bound: Any,
) -> Item:
    record_id = _coerce_id(params.get("id"), ctx)
    vector = _coerce_vector(params.get("vector"), ctx)
    metadata = _coerce_metadata(params.get("metadata"), ctx)
    body = {
        "vectors": [
            {"id": record_id, "values": vector, "metadata": metadata},
        ],
        "namespace": namespace,
    }
    await _request(
        client, cred_cls, cred_payload,
        method="POST",
        url=f"{host}/vectors/upsert",
        json_body=body,
        ctx=ctx,
        bound=bound,
    )
    return Item(
        json={
            "operation": OP_UPSERT,
            "index_name": index_name,
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
    index_name: str,
    host: str,
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
        "topK": top_k,
        "namespace": namespace,
        "includeMetadata": True,
        "includeValues": False,
    }
    response = await _request(
        client, cred_cls, cred_payload,
        method="POST",
        url=f"{host}/query",
        json_body=body,
        ctx=ctx,
        bound=bound,
    )
    matches = _parse_matches(response, metric)
    return Item(
        json={
            "operation": OP_QUERY,
            "index_name": index_name,
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
    index_name: str,
    host: str,
    namespace: str,
    bound: Any,
) -> Item:
    record_id = _coerce_id(params.get("id"), ctx)
    body = {"ids": [record_id], "namespace": namespace}
    await _request(
        client, cred_cls, cred_payload,
        method="POST",
        url=f"{host}/vectors/delete",
        json_body=body,
        ctx=ctx,
        bound=bound,
    )
    return Item(
        json={
            "operation": OP_DELETE,
            "index_name": index_name,
            "namespace": namespace,
            "id": record_id,
        },
    )


async def _do_clear(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    index_name: str,
    host: str,
    namespace: str,
    bound: Any,
) -> Item:
    body = {"deleteAll": True, "namespace": namespace}
    await _request(
        client, cred_cls, cred_payload,
        method="POST",
        url=f"{host}/vectors/delete",
        json_body=body,
        ctx=ctx,
        bound=bound,
    )
    return Item(
        json={
            "operation": OP_CLEAR,
            "index_name": index_name,
            "namespace": namespace,
        },
    )


async def _index_exists(
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    index_name: str,
    ctx: ExecutionContext,
    bound: Any,
) -> bool:
    request = client.build_request(
        "GET", f"{_CONTROL_PLANE_HOST}/indexes/{index_name}",
    )
    await cred_cls.inject(cred_payload, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        bound.error("vector_pinecone.request_failed", error=str(exc))
        msg = f"Vector Pinecone: network error: {exc}"
        raise NodeExecutionError(
            msg, node_id=ctx.node.id, original=exc,
        ) from exc
    if response.status_code == httpx.codes.NOT_FOUND:
        return False
    if response.status_code >= httpx.codes.BAD_REQUEST:
        _raise_for_status(response, ctx, bound)
    return True


async def _resolve_host(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    index_name: str,
    explicit_host: str,
    host_cache: dict[str, str],
    bound: Any,
) -> str:
    if explicit_host:
        return _normalize_host(explicit_host)
    cached = host_cache.get(index_name)
    if cached is not None:
        return cached
    payload = await _request(
        client, cred_cls, cred_payload,
        method="GET",
        url=f"{_CONTROL_PLANE_HOST}/indexes/{index_name}",
        json_body=None,
        ctx=ctx,
        bound=bound,
    )
    host = str(payload.get("host") or "").strip()
    if not host:
        msg = (
            f"Vector Pinecone: control plane did not return a "
            f"data-plane host for index {index_name!r}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    normalized = _normalize_host(host)
    host_cache[index_name] = normalized
    return normalized


def _normalize_host(host: str) -> str:
    cleaned = host.strip().rstrip("/")
    if cleaned.startswith(("http://", "https://")):
        return cleaned
    return f"https://{cleaned}"


async def _request(
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    method: str,
    url: str,
    ctx: ExecutionContext,
    bound: Any,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = client.build_request(method, url, json=json_body)
    await cred_cls.inject(cred_payload, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        bound.error("vector_pinecone.request_failed", error=str(exc))
        msg = f"Vector Pinecone: network error: {exc}"
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
        "vector_pinecone.api_error",
        status=response.status_code,
        error=error,
    )
    msg = f"Vector Pinecone failed (HTTP {response.status_code}): {error}"
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
        message = payload.get("message") or payload.get("error")
        if isinstance(message, str) and message:
            return message
        if isinstance(message, dict):
            inner = message.get("message")
            if isinstance(inner, str) and inner:
                return inner
    return f"HTTP {status_code}"


def _parse_matches(
    payload: dict[str, Any], metric: str,
) -> list[dict[str, Any]]:
    matches_raw = payload.get("matches")
    if not isinstance(matches_raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in matches_raw:
        if not isinstance(entry, dict):
            continue
        score = entry.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            continue
        normalized = _score_from_pinecone(metric, float(score))
        meta = entry.get("metadata")
        out.append(
            {
                "id": entry.get("id"),
                "metadata": dict(meta) if isinstance(meta, dict) else {},
                "score": normalized,
            },
        )
    return out


def _score_from_pinecone(metric: str, raw: float) -> float:
    # Pinecone returns squared L2 distance for euclidean (lower is
    # closer) and similarity for cosine / dotproduct (higher is
    # closer). Negating euclidean keeps "higher = more similar"
    # uniform across every retrieval backend.
    if metric == METRIC_EUCLIDEAN:
        return -raw
    return raw


def _coerce_id(raw: Any, ctx: ExecutionContext) -> str:
    if isinstance(raw, bool):  # bool is a subclass of int - reject early.
        msg = "Vector Pinecone: 'id' must be a string"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, int):
        return str(raw)
    msg = "Vector Pinecone: 'id' is required"
    raise NodeExecutionError(msg, node_id=ctx.node.id)


def _coerce_vector(raw: Any, ctx: ExecutionContext) -> list[float]:
    if not isinstance(raw, list) or not raw:
        msg = (
            "Vector Pinecone: 'vector' must be a non-empty JSON array "
            "of numbers"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    out: list[float] = []
    for entry in raw:
        if isinstance(entry, bool) or not isinstance(entry, (int, float)):
            msg = "Vector Pinecone: every 'vector' element must be a number"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        out.append(float(entry))
    return out


def _coerce_metadata(raw: Any, ctx: ExecutionContext) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        msg = "Vector Pinecone: 'metadata' must be a JSON object"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return dict(raw)


def _coerce_metric(raw: Any, ctx: ExecutionContext) -> str:
    metric = str(raw or _DEFAULT_METRIC)
    if metric not in _SUPPORTED_METRICS:
        msg = f"Vector Pinecone: unsupported metric {metric!r}"
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
            f"Vector Pinecone: {field!r} must be an integer",
            node_id=ctx.node.id,
            original=exc,
        ) from exc
    if value < 1:
        msg = f"Vector Pinecone: {field!r} must be >= 1"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return value
