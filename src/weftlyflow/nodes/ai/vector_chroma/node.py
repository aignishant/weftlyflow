"""Vector Chroma node - self-hosted vector store via Chroma REST.

Same operation surface as :mod:`weftlyflow.nodes.ai.vector_memory`,
:mod:`weftlyflow.nodes.ai.vector_pgvector`,
:mod:`weftlyflow.nodes.ai.vector_qdrant`, and
:mod:`weftlyflow.nodes.ai.vector_pinecone`: swapping backends is a
one-property change. Chroma's REST API is single-host but data-plane
operations are keyed on a collection *UUID* rather than the
user-friendly name, so the node performs a ``GET`` on the collection
path per ``execute`` call and caches the resolved id for the rest of
the batch.

Paths are v2-style and tenant/database-scoped; both default to
Chroma's out-of-the-box ``default_tenant`` / ``default_database``
but the credential can override either.

Metric mapping (Chroma calls this the HNSW "space"):

* ``cosine``    -> ``cosine`` (returns cosine distance, 0 = identical).
* ``dot``       -> ``ip``     (returns negative inner product).
* ``euclidean`` -> ``l2``     (returns squared L2 distance).

Every metric returns a *distance* where lower is closer, so the
score is flipped to ``-raw`` to keep "higher = more similar"
consistent across every retrieval backend.

Chroma has no native namespace concept; we store a
``_weftlyflow_namespace`` key inside each vector's metadata and
filter on it via Chroma's ``where`` clause on every query / delete /
clear. The marker is stripped from surfaced matches.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.chroma_api import (
    base_url_from,
    database_from,
    tenant_from,
)
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


_CREDENTIAL_SLOT: str = "chroma"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.chroma",)

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

_METRIC_TO_CHROMA: dict[str, str] = {
    METRIC_COSINE: "cosine",
    METRIC_DOT: "ip",
    METRIC_EUCLIDEAN: "l2",
}

_DEFAULT_COLLECTION: str = "weftlyflow_vectors"
_DEFAULT_NAMESPACE: str = "default"
_DEFAULT_TOP_K: int = 5
_DEFAULT_METRIC: str = METRIC_COSINE
_DEFAULT_TIMEOUT_SECONDS: float = 30.0
_NAMESPACE_META_KEY: str = "_weftlyflow_namespace"

log = structlog.get_logger(__name__)


class VectorChromaNode(BaseNode):
    """Self-hosted vector store backed by the Chroma REST API."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.vector_chroma",
        version=1,
        display_name="Vector Chroma",
        description=(
            "Self-hosted vector store backed by Chroma. Same upsert / "
            "query / delete / clear surface as vector_memory so the "
            "backends are swappable."
        ),
        icon="icons/vector-chroma.svg",
        category=NodeCategory.AI,
        group=["ai", "retrieval"],
        documentation_url="https://docs.trychroma.com/reference/python/client",
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
                description="Chroma collection that hosts the vectors.",
            ),
            PropertySchema(
                name="namespace",
                display_name="Namespace",
                type="string",
                default=_DEFAULT_NAMESPACE,
                description=(
                    "Metadata-scoped partition stored under "
                    f"'{_NAMESPACE_META_KEY}' and filtered via Chroma's "
                    "'where' clause on every query / delete / clear."
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
                name="document",
                display_name="Document",
                type="string",
                description=(
                    "Optional raw document text to store alongside the "
                    "vector. Chroma stores it verbatim and returns it "
                    "on query when present."
                ),
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
                    "Used by 'ensure_schema' (HNSW space) and 'query' "
                    "(score normalisation)."
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
        """Dispatch each input item to the appropriate Chroma operation."""
        cred_cls, cred_payload = await _resolve_credential(ctx)
        base_url = base_url_from(str(cred_payload.get("base_url") or ""))
        tenant = tenant_from(str(cred_payload.get("tenant") or ""))
        database = database_from(str(cred_payload.get("database") or ""))
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        seed = items or [Item()]
        emitted: list[Item] = []
        id_cache: dict[str, str] = {}
        async with httpx.AsyncClient(
            base_url=base_url, timeout=_DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                emitted.append(
                    await _run_one(
                        ctx, client, cred_cls, cred_payload,
                        tenant=tenant,
                        database=database,
                        item=item,
                        id_cache=id_cache,
                        bound=bound,
                    ),
                )
        return [emitted]


async def _resolve_credential(
    ctx: ExecutionContext,
) -> tuple[BaseCredentialType, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Vector Chroma: a chroma credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return credential


async def _run_one(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    tenant: str,
    database: str,
    item: Item,
    id_cache: dict[str, str],
    bound: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_QUERY).strip()
    if operation not in _SUPPORTED_OPERATIONS:
        msg = f"Vector Chroma: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    raw_collection = params.get("collection")
    collection = (
        _DEFAULT_COLLECTION
        if raw_collection is None
        else str(raw_collection).strip()
    )
    if not collection:
        msg = "Vector Chroma: 'collection' is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    if operation == OP_ENSURE_SCHEMA:
        return await _do_ensure_schema(
            ctx, client, cred_cls, cred_payload,
            params=params,
            tenant=tenant,
            database=database,
            collection=collection,
            bound=bound,
        )

    # Validate operation-specific inputs before hitting the network so
    # bad inputs fail fast without burning a collection lookup.
    if operation == OP_UPSERT:
        _coerce_id(params.get("id"), ctx)
        _coerce_vector(params.get("vector"), ctx)
        _coerce_document(params.get("document"), ctx)
    elif operation == OP_QUERY:
        _coerce_vector(params.get("vector"), ctx)
        _coerce_positive_int(
            params.get("top_k"), ctx, field="top_k", default=_DEFAULT_TOP_K,
        )
        _coerce_metric(params.get("metric") or _DEFAULT_METRIC, ctx)
    elif operation == OP_DELETE:
        _coerce_id(params.get("id"), ctx)

    collection_id = await _resolve_collection_id(
        ctx, client, cred_cls, cred_payload,
        tenant=tenant,
        database=database,
        collection=collection,
        id_cache=id_cache,
        bound=bound,
    )
    namespace = str(params.get("namespace") or _DEFAULT_NAMESPACE)
    if operation == OP_UPSERT:
        return await _do_upsert(
            ctx, client, cred_cls, cred_payload,
            params=params,
            tenant=tenant,
            database=database,
            collection=collection,
            collection_id=collection_id,
            namespace=namespace,
            bound=bound,
        )
    if operation == OP_QUERY:
        return await _do_query(
            ctx, client, cred_cls, cred_payload,
            params=params,
            tenant=tenant,
            database=database,
            collection=collection,
            collection_id=collection_id,
            namespace=namespace,
            bound=bound,
        )
    if operation == OP_DELETE:
        return await _do_delete(
            ctx, client, cred_cls, cred_payload,
            params=params,
            tenant=tenant,
            database=database,
            collection=collection,
            collection_id=collection_id,
            namespace=namespace,
            bound=bound,
        )
    return await _do_clear(
        ctx, client, cred_cls, cred_payload,
        tenant=tenant,
        database=database,
        collection=collection,
        collection_id=collection_id,
        namespace=namespace,
        bound=bound,
    )


async def _do_ensure_schema(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    params: dict[str, Any],
    tenant: str,
    database: str,
    collection: str,
    bound: Any,
) -> Item:
    metric = _coerce_metric(params.get("metric") or _DEFAULT_METRIC, ctx)
    existing = await _get_collection(
        client, cred_cls, cred_payload,
        tenant=tenant, database=database, collection=collection,
        ctx=ctx, bound=bound,
    )
    if existing is not None:
        return Item(
            json={
                "operation": OP_ENSURE_SCHEMA,
                "collection": collection,
                "collection_id": existing.get("id"),
                "metric": metric,
                "created": False,
            },
        )
    body = {
        "name": collection,
        "configuration": {"hnsw": {"space": _METRIC_TO_CHROMA[metric]}},
    }
    payload = await _request(
        client, cred_cls, cred_payload,
        method="POST",
        path=_collections_path(tenant, database),
        json_body=body,
        ctx=ctx,
        bound=bound,
    )
    return Item(
        json={
            "operation": OP_ENSURE_SCHEMA,
            "collection": collection,
            "collection_id": payload.get("id"),
            "metric": metric,
            "created": True,
        },
    )


async def _do_upsert(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    params: dict[str, Any],
    tenant: str,
    database: str,
    collection: str,
    collection_id: str,
    namespace: str,
    bound: Any,
) -> Item:
    record_id = _coerce_id(params.get("id"), ctx)
    vector = _coerce_vector(params.get("vector"), ctx)
    metadata = _coerce_metadata(params.get("metadata"), ctx)
    metadata[_NAMESPACE_META_KEY] = namespace
    document = _coerce_document(params.get("document"), ctx)
    body: dict[str, Any] = {
        "ids": [record_id],
        "embeddings": [vector],
        "metadatas": [metadata],
    }
    if document is not None:
        body["documents"] = [document]
    await _request(
        client, cred_cls, cred_payload,
        method="POST",
        path=f"{_collections_path(tenant, database)}/{collection_id}/upsert",
        json_body=body,
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
    *,
    params: dict[str, Any],
    tenant: str,
    database: str,
    collection: str,
    collection_id: str,
    namespace: str,
    bound: Any,
) -> Item:
    vector = _coerce_vector(params.get("vector"), ctx)
    top_k = _coerce_positive_int(
        params.get("top_k"), ctx, field="top_k", default=_DEFAULT_TOP_K,
    )
    metric = _coerce_metric(params.get("metric") or _DEFAULT_METRIC, ctx)
    body = {
        "query_embeddings": [vector],
        "n_results": top_k,
        "where": {_NAMESPACE_META_KEY: namespace},
        "include": ["metadatas", "documents", "distances"],
    }
    response = await _request(
        client, cred_cls, cred_payload,
        method="POST",
        path=f"{_collections_path(tenant, database)}/{collection_id}/query",
        json_body=body,
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
    *,
    params: dict[str, Any],
    tenant: str,
    database: str,
    collection: str,
    collection_id: str,
    namespace: str,
    bound: Any,
) -> Item:
    record_id = _coerce_id(params.get("id"), ctx)
    # Scope delete to (id, namespace) via the where clause so an id
    # collision from another namespace cannot take out an unrelated
    # row.
    body = {
        "ids": [record_id],
        "where": {_NAMESPACE_META_KEY: namespace},
    }
    await _request(
        client, cred_cls, cred_payload,
        method="POST",
        path=f"{_collections_path(tenant, database)}/{collection_id}/delete",
        json_body=body,
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
    *,
    tenant: str,
    database: str,
    collection: str,
    collection_id: str,
    namespace: str,
    bound: Any,
) -> Item:
    body = {"where": {_NAMESPACE_META_KEY: namespace}}
    await _request(
        client, cred_cls, cred_payload,
        method="POST",
        path=f"{_collections_path(tenant, database)}/{collection_id}/delete",
        json_body=body,
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


async def _get_collection(
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    tenant: str,
    database: str,
    collection: str,
    ctx: ExecutionContext,
    bound: Any,
) -> dict[str, Any] | None:
    path = f"{_collections_path(tenant, database)}/{collection}"
    request = client.build_request("GET", path)
    await cred_cls.inject(cred_payload, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        bound.error("vector_chroma.request_failed", error=str(exc))
        msg = f"Vector Chroma: network error: {exc}"
        raise NodeExecutionError(
            msg, node_id=ctx.node.id, original=exc,
        ) from exc
    if response.status_code == httpx.codes.NOT_FOUND:
        return None
    if response.status_code >= httpx.codes.BAD_REQUEST:
        _raise_for_status(response, ctx, bound)
    return _safe_json(response)


async def _resolve_collection_id(
    ctx: ExecutionContext,
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    tenant: str,
    database: str,
    collection: str,
    id_cache: dict[str, str],
    bound: Any,
) -> str:
    cache_key = f"{tenant}/{database}/{collection}"
    cached = id_cache.get(cache_key)
    if cached is not None:
        return cached
    payload = await _get_collection(
        client, cred_cls, cred_payload,
        tenant=tenant, database=database, collection=collection,
        ctx=ctx, bound=bound,
    )
    if payload is None:
        msg = (
            f"Vector Chroma: collection {collection!r} does not exist; "
            f"run the 'ensure_schema' op first"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    collection_id = str(payload.get("id") or "").strip()
    if not collection_id:
        msg = (
            f"Vector Chroma: control plane did not return an id for "
            f"collection {collection!r}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    id_cache[cache_key] = collection_id
    return collection_id


def _collections_path(tenant: str, database: str) -> str:
    return f"/api/v2/tenants/{tenant}/databases/{database}/collections"


async def _request(
    client: httpx.AsyncClient,
    cred_cls: BaseCredentialType,
    cred_payload: dict[str, Any],
    *,
    method: str,
    path: str,
    ctx: ExecutionContext,
    bound: Any,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = client.build_request(method, path, json=json_body)
    await cred_cls.inject(cred_payload, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        bound.error("vector_chroma.request_failed", error=str(exc))
        msg = f"Vector Chroma: network error: {exc}"
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
        "vector_chroma.api_error",
        status=response.status_code,
        error=error,
    )
    msg = f"Vector Chroma failed (HTTP {response.status_code}): {error}"
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
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                inner = value.get("message") or value.get("detail")
                if isinstance(inner, str) and inner:
                    return inner
    return f"HTTP {status_code}"


def _parse_matches(
    payload: dict[str, Any], metric: str,
) -> list[dict[str, Any]]:
    # Chroma returns every result column as a list-of-lists because a
    # single call can carry multiple query vectors. We only ever send
    # one query vector per call so the zeroth slot is always the right
    # row to read.
    ids_row = _first_row(payload.get("ids"))
    if ids_row is None:
        return []
    distances_row = _first_row(payload.get("distances")) or []
    metadatas_row = _first_row(payload.get("metadatas")) or []
    documents_row = _first_row(payload.get("documents")) or []
    out: list[dict[str, Any]] = []
    for idx, record_id in enumerate(ids_row):
        raw_distance = (
            distances_row[idx] if idx < len(distances_row) else None
        )
        if (
            not isinstance(raw_distance, (int, float))
            or isinstance(raw_distance, bool)
        ):
            continue
        metadata_entry = (
            metadatas_row[idx] if idx < len(metadatas_row) else None
        )
        metadata = (
            dict(metadata_entry)
            if isinstance(metadata_entry, dict)
            else {}
        )
        metadata.pop(_NAMESPACE_META_KEY, None)
        document = (
            documents_row[idx] if idx < len(documents_row) else None
        )
        out.append(
            {
                "id": record_id,
                "metadata": metadata,
                "document": document if isinstance(document, str) else None,
                "score": _score_from_chroma(metric, float(raw_distance)),
            },
        )
    return out


def _first_row(column: Any) -> list[Any] | None:
    if not isinstance(column, list) or not column:
        return None
    first = column[0]
    return first if isinstance(first, list) else None


def _score_from_chroma(metric: str, raw: float) -> float:
    # Chroma returns a distance for every space - lower = closer.
    # Flip the sign so "higher = more similar" is uniform across
    # backends. For cosine the magnitude is still a distance, not a
    # similarity, but callers that only care about ordering get the
    # right comparison.
    del metric  # Signature kept uniform with other backends.
    return -raw


def _coerce_id(raw: Any, ctx: ExecutionContext) -> str:
    if isinstance(raw, bool):  # bool is a subclass of int - reject early.
        msg = "Vector Chroma: 'id' must be a string"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, int):
        return str(raw)
    msg = "Vector Chroma: 'id' is required"
    raise NodeExecutionError(msg, node_id=ctx.node.id)


def _coerce_vector(raw: Any, ctx: ExecutionContext) -> list[float]:
    if not isinstance(raw, list) or not raw:
        msg = (
            "Vector Chroma: 'vector' must be a non-empty JSON array "
            "of numbers"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    out: list[float] = []
    for entry in raw:
        if isinstance(entry, bool) or not isinstance(entry, (int, float)):
            msg = "Vector Chroma: every 'vector' element must be a number"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        out.append(float(entry))
    return out


def _coerce_metadata(raw: Any, ctx: ExecutionContext) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        msg = "Vector Chroma: 'metadata' must be a JSON object"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return dict(raw)


def _coerce_document(raw: Any, ctx: ExecutionContext) -> str | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        msg = "Vector Chroma: 'document' must be a string"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return raw


def _coerce_metric(raw: Any, ctx: ExecutionContext) -> str:
    metric = str(raw or _DEFAULT_METRIC)
    if metric not in _SUPPORTED_METRICS:
        msg = f"Vector Chroma: unsupported metric {metric!r}"
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
            f"Vector Chroma: {field!r} must be an integer",
            node_id=ctx.node.id,
            original=exc,
        ) from exc
    if value < 1:
        msg = f"Vector Chroma: {field!r} must be >= 1"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return value
