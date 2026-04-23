"""Per-operation request builders for the Box node.

Each builder returns ``(http_method, path, body, query)``. Paths are
prefixed with :data:`API_BASE_URL` by the node layer.

Box folder/file IDs are opaque numeric strings; the root folder is the
literal ``"0"``. The ``search`` endpoint accepts ``query`` + a
comma-separated ``content_types`` / ``ancestor_folder_ids`` filter
pair and paginates through offset+limit.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.box.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    OP_COPY_FILE,
    OP_CREATE_FOLDER,
    OP_DELETE_FILE,
    OP_GET_FILE,
    OP_LIST_FOLDER,
    OP_LIST_USERS,
    OP_SEARCH,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Box: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_folder(params: dict[str, Any]) -> RequestSpec:
    folder_id = str(params.get("folder_id") or "0").strip() or "0"
    query: dict[str, Any] = {"limit": _coerce_page_size(params.get("limit"))}
    offset = params.get("offset")
    if offset is not None and offset != "":
        query["offset"] = _coerce_non_negative_int(offset, field="offset")
    fields = _coerce_string_list(params.get("fields"), field="fields")
    if fields:
        query["fields"] = ",".join(fields)
    return "GET", f"/folders/{quote(folder_id, safe='')}/items", None, query


def _build_get_file(params: dict[str, Any]) -> RequestSpec:
    file_id = _required(params, "file_id")
    fields = _coerce_string_list(params.get("fields"), field="fields")
    query: dict[str, Any] = {}
    if fields:
        query["fields"] = ",".join(fields)
    return "GET", f"/files/{quote(file_id, safe='')}", None, query


def _build_delete_file(params: dict[str, Any]) -> RequestSpec:
    file_id = _required(params, "file_id")
    return "DELETE", f"/files/{quote(file_id, safe='')}", None, {}


def _build_create_folder(params: dict[str, Any]) -> RequestSpec:
    name = _required(params, "name")
    parent_id = str(params.get("parent_id") or "0").strip() or "0"
    body: dict[str, Any] = {"name": name, "parent": {"id": parent_id}}
    return "POST", "/folders", body, {}


def _build_copy_file(params: dict[str, Any]) -> RequestSpec:
    file_id = _required(params, "file_id")
    parent_id = _required(params, "parent_id")
    body: dict[str, Any] = {"parent": {"id": parent_id}}
    new_name = str(params.get("new_name") or "").strip()
    if new_name:
        body["name"] = new_name
    return "POST", f"/files/{quote(file_id, safe='')}/copy", body, {}


def _build_search(params: dict[str, Any]) -> RequestSpec:
    query_text = _required(params, "query")
    query: dict[str, Any] = {
        "query": query_text,
        "limit": _coerce_page_size(params.get("limit")),
    }
    content_types = _coerce_string_list(
        params.get("content_types"), field="content_types",
    )
    if content_types:
        query["content_types"] = ",".join(content_types)
    ancestor_ids = _coerce_string_list(
        params.get("ancestor_folder_ids"), field="ancestor_folder_ids",
    )
    if ancestor_ids:
        query["ancestor_folder_ids"] = ",".join(ancestor_ids)
    file_extensions = _coerce_string_list(
        params.get("file_extensions"), field="file_extensions",
    )
    if file_extensions:
        query["file_extensions"] = ",".join(file_extensions)
    return "GET", "/search", None, query


def _build_list_users(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_page_size(params.get("limit"))}
    filter_term = str(params.get("filter_term") or "").strip()
    if filter_term:
        query["filter_term"] = filter_term
    user_type = str(params.get("user_type") or "").strip()
    if user_type:
        query["user_type"] = user_type
    return "GET", "/users", None, query


def _coerce_non_negative_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Box: {field!r} must be a non-negative integer"
        raise ValueError(msg) from exc
    return max(0, value)


def _coerce_page_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Box: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Box: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_SIZE)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Box: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Box: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_FOLDER: _build_list_folder,
    OP_GET_FILE: _build_get_file,
    OP_DELETE_FILE: _build_delete_file,
    OP_CREATE_FOLDER: _build_create_folder,
    OP_COPY_FILE: _build_copy_file,
    OP_SEARCH: _build_search,
    OP_LIST_USERS: _build_list_users,
}
