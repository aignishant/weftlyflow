"""Per-operation request builders for the Algolia Search v1 node.

Each builder returns ``(http_method, path, json_body, query_params, use_write_host)``.
The ``use_write_host`` flag tells the node layer whether to route the
call to ``<app>.algolia.net`` (indexing) or ``<app>-dsn.algolia.net``
(read operations).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.algolia.constants import (
    API_VERSION_PREFIX,
    DEFAULT_HITS_PER_PAGE,
    MAX_HITS_PER_PAGE,
    OP_ADD_OBJECT,
    OP_DELETE_OBJECT,
    OP_GET_OBJECT,
    OP_LIST_INDICES,
    OP_SEARCH,
    OP_UPDATE_OBJECT,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any], bool]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Algolia: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_search(params: dict[str, Any]) -> RequestSpec:
    index_name = _required(params, "index_name")
    body: dict[str, Any] = {
        "query": str(params.get("query") or ""),
        "hitsPerPage": _coerce_limit(params.get("hits_per_page")),
    }
    page = params.get("page")
    if page is not None and page != "":
        try:
            page_value = int(page)
        except (TypeError, ValueError) as exc:
            msg = "Algolia: 'page' must be an integer"
            raise ValueError(msg) from exc
        if page_value < 0:
            msg = "Algolia: 'page' must be >= 0"
            raise ValueError(msg)
        body["page"] = page_value
    filters = str(params.get("filters") or "").strip()
    if filters:
        body["filters"] = filters
    extra = params.get("extra_params")
    if extra is not None:
        if not isinstance(extra, dict):
            msg = "Algolia: 'extra_params' must be a JSON object"
            raise ValueError(msg)
        body.update(extra)
    path = f"{API_VERSION_PREFIX}/indexes/{quote(index_name, safe='')}/query"
    return "POST", path, body, {}, False


def _build_add_object(params: dict[str, Any]) -> RequestSpec:
    index_name = _required(params, "index_name")
    obj = params.get("object")
    if not isinstance(obj, dict) or not obj:
        msg = "Algolia: 'object' must be a non-empty JSON object"
        raise ValueError(msg)
    path = f"{API_VERSION_PREFIX}/indexes/{quote(index_name, safe='')}"
    return "POST", path, dict(obj), {}, True


def _build_update_object(params: dict[str, Any]) -> RequestSpec:
    index_name = _required(params, "index_name")
    object_id = _required(params, "object_id")
    obj = params.get("object")
    if not isinstance(obj, dict) or not obj:
        msg = "Algolia: 'object' must be a non-empty JSON object"
        raise ValueError(msg)
    body = dict(obj)
    body["objectID"] = object_id
    path = (
        f"{API_VERSION_PREFIX}/indexes/{quote(index_name, safe='')}"
        f"/{quote(object_id, safe='')}"
    )
    return "PUT", path, body, {}, True


def _build_get_object(params: dict[str, Any]) -> RequestSpec:
    index_name = _required(params, "index_name")
    object_id = _required(params, "object_id")
    path = (
        f"{API_VERSION_PREFIX}/indexes/{quote(index_name, safe='')}"
        f"/{quote(object_id, safe='')}"
    )
    return "GET", path, None, {}, False


def _build_delete_object(params: dict[str, Any]) -> RequestSpec:
    index_name = _required(params, "index_name")
    object_id = _required(params, "object_id")
    path = (
        f"{API_VERSION_PREFIX}/indexes/{quote(index_name, safe='')}"
        f"/{quote(object_id, safe='')}"
    )
    return "DELETE", path, None, {}, True


def _build_list_indices(_: dict[str, Any]) -> RequestSpec:
    return "GET", f"{API_VERSION_PREFIX}/indexes", None, {}, False


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Algolia: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_HITS_PER_PAGE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Algolia: 'hits_per_page' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Algolia: 'hits_per_page' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_HITS_PER_PAGE)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SEARCH: _build_search,
    OP_ADD_OBJECT: _build_add_object,
    OP_UPDATE_OBJECT: _build_update_object,
    OP_GET_OBJECT: _build_get_object,
    OP_DELETE_OBJECT: _build_delete_object,
    OP_LIST_INDICES: _build_list_indices,
}
