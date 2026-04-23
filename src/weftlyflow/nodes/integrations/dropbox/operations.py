"""Per-operation request builders for the Dropbox node.

Each builder returns ``(base_url, path, body, arg_header)`` where:

* ``base_url`` routes RPC operations to ``api.dropboxapi.com`` and
  content operations to ``content.dropboxapi.com``.
* ``body`` is the JSON body for RPC endpoints, or ``None`` for content
  endpoints.
* ``arg_header`` is the *JSON-encoded* value of the ``Dropbox-API-Arg``
  header — Dropbox's distinctive pattern where content operations carry
  their argument blob in a header rather than a body so the HTTP body
  is free for raw file bytes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.dropbox.constants import (
    API_BASE_URL,
    CONTENT_BASE_URL,
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    OP_COPY,
    OP_CREATE_FOLDER,
    OP_DELETE,
    OP_DOWNLOAD,
    OP_GET_METADATA,
    OP_LIST_FOLDER,
    OP_MOVE,
    OP_SEARCH,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, str | None]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Dropbox: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_folder(params: dict[str, Any]) -> RequestSpec:
    path = _required_path(params, "path")
    body: dict[str, Any] = {"path": path, "recursive": bool(params.get("recursive"))}
    return API_BASE_URL, "/2/files/list_folder", body, None


def _build_get_metadata(params: dict[str, Any]) -> RequestSpec:
    path = _required_path(params, "path")
    body: dict[str, Any] = {"path": path}
    return API_BASE_URL, "/2/files/get_metadata", body, None


def _build_create_folder(params: dict[str, Any]) -> RequestSpec:
    path = _required_path(params, "path")
    body: dict[str, Any] = {
        "path": path,
        "autorename": bool(params.get("autorename")),
    }
    return API_BASE_URL, "/2/files/create_folder_v2", body, None


def _build_delete(params: dict[str, Any]) -> RequestSpec:
    path = _required_path(params, "path")
    body: dict[str, Any] = {"path": path}
    return API_BASE_URL, "/2/files/delete_v2", body, None


def _build_move(params: dict[str, Any]) -> RequestSpec:
    from_path = _required_path(params, "from_path")
    to_path = _required_path(params, "to_path")
    body: dict[str, Any] = {
        "from_path": from_path,
        "to_path": to_path,
        "autorename": bool(params.get("autorename")),
        "allow_shared_folder": bool(params.get("allow_shared_folder")),
    }
    return API_BASE_URL, "/2/files/move_v2", body, None


def _build_copy(params: dict[str, Any]) -> RequestSpec:
    from_path = _required_path(params, "from_path")
    to_path = _required_path(params, "to_path")
    body: dict[str, Any] = {
        "from_path": from_path,
        "to_path": to_path,
        "autorename": bool(params.get("autorename")),
    }
    return API_BASE_URL, "/2/files/copy_v2", body, None


def _build_search(params: dict[str, Any]) -> RequestSpec:
    query = _required(params, "query")
    options: dict[str, Any] = {"max_results": _coerce_limit(params.get("limit"))}
    path_scope = str(params.get("path") or "").strip()
    if path_scope:
        options["path"] = path_scope
    body: dict[str, Any] = {"query": query, "options": options}
    return API_BASE_URL, "/2/files/search_v2", body, None


def _build_download(params: dict[str, Any]) -> RequestSpec:
    path = _required_path(params, "path")
    arg = json.dumps({"path": path}, separators=(",", ":"))
    return CONTENT_BASE_URL, "/2/files/download", None, arg


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_SEARCH_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Dropbox: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Dropbox: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_SEARCH_LIMIT)


def _required_path(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Dropbox: {key!r} is required"
        raise ValueError(msg)
    if not value.startswith("/") and not value.startswith("id:") and not value.startswith("rev:"):
        msg = f"Dropbox: {key!r} must start with '/', 'id:', or 'rev:'"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Dropbox: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_FOLDER: _build_list_folder,
    OP_GET_METADATA: _build_get_metadata,
    OP_CREATE_FOLDER: _build_create_folder,
    OP_DELETE: _build_delete,
    OP_MOVE: _build_move,
    OP_COPY: _build_copy,
    OP_SEARCH: _build_search,
    OP_DOWNLOAD: _build_download,
}
