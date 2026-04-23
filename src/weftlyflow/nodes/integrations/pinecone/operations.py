"""Per-operation request builders for the Pinecone node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to either the control-plane host (``https://api.pinecone.io``,
for ``list_indexes`` / ``describe_index``) or the caller-supplied
per-index data-plane host for vector operations.

Distinctive Pinecone shapes:

* Data-plane vector writes accept a plural-key envelope — upserts send
  ``{"vectors": [...], "namespace": str}``; deletes send
  ``{"ids": [...], "namespace": str}`` or ``{"deleteAll": true,
  "namespace": str}``.
* ``fetch_vectors`` is the only vector op that uses ``GET`` — ids are
  repeated query-string params and multiple ``?ids=...`` pairs are the
  idiomatic on-the-wire shape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.pinecone.constants import (
    OP_DELETE_VECTORS,
    OP_DESCRIBE_INDEX,
    OP_FETCH_VECTORS,
    OP_LIST_INDEXES,
    OP_QUERY_VECTORS,
    OP_UPSERT_VECTORS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Pinecone: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_indexes(_: dict[str, Any]) -> RequestSpec:
    return "GET", "/indexes", None, {}


def _build_describe_index(params: dict[str, Any]) -> RequestSpec:
    name = _required(params, "index_name")
    return "GET", f"/indexes/{quote(name, safe='')}", None, {}


def _build_query_vectors(params: dict[str, Any]) -> RequestSpec:
    top_k = _required_int(params, "top_k")
    body: dict[str, Any] = {"topK": top_k}
    vector = params.get("vector")
    if isinstance(vector, list) and vector:
        body["vector"] = [float(value) for value in vector]
    vector_id = str(params.get("id") or "").strip()
    if vector_id:
        body["id"] = vector_id
    if "vector" not in body and "id" not in body:
        msg = "Pinecone: query requires either 'vector' or 'id'"
        raise ValueError(msg)
    namespace = str(params.get("namespace") or "").strip()
    if namespace:
        body["namespace"] = namespace
    include_values = params.get("include_values")
    if isinstance(include_values, bool):
        body["includeValues"] = include_values
    include_metadata = params.get("include_metadata")
    if isinstance(include_metadata, bool):
        body["includeMetadata"] = include_metadata
    filter_obj = params.get("filter")
    if isinstance(filter_obj, dict) and filter_obj:
        body["filter"] = filter_obj
    return "POST", "/query", body, {}


def _build_upsert_vectors(params: dict[str, Any]) -> RequestSpec:
    vectors = params.get("vectors")
    if not isinstance(vectors, list) or not vectors:
        msg = "Pinecone: 'vectors' must be a non-empty list"
        raise ValueError(msg)
    body: dict[str, Any] = {"vectors": vectors}
    namespace = str(params.get("namespace") or "").strip()
    if namespace:
        body["namespace"] = namespace
    return "POST", "/vectors/upsert", body, {}


def _build_fetch_vectors(params: dict[str, Any]) -> RequestSpec:
    ids = params.get("ids")
    if not isinstance(ids, list) or not ids:
        msg = "Pinecone: 'ids' must be a non-empty list"
        raise ValueError(msg)
    query: dict[str, Any] = {"ids": [str(value) for value in ids]}
    namespace = str(params.get("namespace") or "").strip()
    if namespace:
        query["namespace"] = namespace
    return "GET", "/vectors/fetch", None, query


def _build_delete_vectors(params: dict[str, Any]) -> RequestSpec:
    body: dict[str, Any] = {}
    delete_all = params.get("delete_all")
    ids = params.get("ids")
    if delete_all is True:
        body["deleteAll"] = True
    elif isinstance(ids, list) and ids:
        body["ids"] = [str(value) for value in ids]
    else:
        msg = "Pinecone: delete requires 'ids' or 'delete_all=true'"
        raise ValueError(msg)
    namespace = str(params.get("namespace") or "").strip()
    if namespace:
        body["namespace"] = namespace
    filter_obj = params.get("filter")
    if isinstance(filter_obj, dict) and filter_obj:
        body["filter"] = filter_obj
    return "POST", "/vectors/delete", body, {}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Pinecone: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_int(params: dict[str, Any], key: str) -> int:
    raw: Any = params.get(key)
    if raw in (None, ""):
        msg = f"Pinecone: {key!r} is required"
        raise ValueError(msg)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Pinecone: {key!r} must be an integer"
        raise ValueError(msg) from exc
    if value <= 0:
        msg = f"Pinecone: {key!r} must be positive"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_INDEXES: _build_list_indexes,
    OP_DESCRIBE_INDEX: _build_describe_index,
    OP_QUERY_VECTORS: _build_query_vectors,
    OP_UPSERT_VECTORS: _build_upsert_vectors,
    OP_FETCH_VECTORS: _build_fetch_vectors,
    OP_DELETE_VECTORS: _build_delete_vectors,
}
