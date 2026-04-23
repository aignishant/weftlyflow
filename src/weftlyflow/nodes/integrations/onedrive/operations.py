"""Per-operation request builders for the OneDrive node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://graph.microsoft.com/v1.0``. Upload bodies are
*not* generated here — they are binary and handled directly by the node
(either in a single PUT for ``upload_small`` or streamed in Content-Range
chunks for ``upload_large``).

Distinctive OneDrive shape:

* Small uploads (<4 MiB) PUT directly to
  ``/me/drive/root:/{path}:/content`` with the raw bytes as the body.
* **Large uploads** first ``POST /createUploadSession`` to get a short-
  lived ``uploadUrl``, then PUT successive byte ranges to that URL with
  ``Content-Range: bytes X-Y/TOTAL`` and ``Content-Length`` on each
  chunk. The final chunk returns the ``driveItem`` JSON; intermediate
  chunks return HTTP 202 with a ``nextExpectedRanges`` array. No other
  provider in the catalog ships this session-based resumable pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.onedrive.constants import (
    DRIVE_ROOT_PREFIX,
    OP_DELETE_ITEM,
    OP_DOWNLOAD_ITEM,
    OP_GET_ITEM,
    OP_LIST_CHILDREN,
    OP_UPLOAD_LARGE,
    OP_UPLOAD_SMALL,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"OneDrive: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_children(params: dict[str, Any]) -> RequestSpec:
    folder = str(params.get("folder_path") or "").strip("/")
    if folder:
        path = f"{DRIVE_ROOT_PREFIX}/root:/{_encode_path(folder)}:/children"
    else:
        path = f"{DRIVE_ROOT_PREFIX}/root/children"
    query: dict[str, Any] = {}
    for key in ("$top", "$skip", "$orderby", "$select", "$filter"):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = str(value)
    return "GET", path, None, query


def _build_get_item(params: dict[str, Any]) -> RequestSpec:
    return "GET", _item_path(params), None, {}


def _build_upload_small(params: dict[str, Any]) -> RequestSpec:
    file_path = _required(params, "file_path").lstrip("/")
    path = f"{DRIVE_ROOT_PREFIX}/root:/{_encode_path(file_path)}:/content"
    conflict = str(params.get("conflict_behavior") or "").strip()
    query: dict[str, Any] = {}
    if conflict:
        query["@microsoft.graph.conflictBehavior"] = conflict
    return "PUT", path, None, query


def _build_upload_large(params: dict[str, Any]) -> RequestSpec:
    file_path = _required(params, "file_path").lstrip("/")
    path = f"{DRIVE_ROOT_PREFIX}/root:/{_encode_path(file_path)}:/createUploadSession"
    body: dict[str, Any] = {
        "item": {
            "@microsoft.graph.conflictBehavior": str(
                params.get("conflict_behavior") or "replace",
            ),
        },
    }
    return "POST", path, body, {}


def _build_download_item(params: dict[str, Any]) -> RequestSpec:
    return "GET", f"{_item_path(params)}/content", None, {}


def _build_delete_item(params: dict[str, Any]) -> RequestSpec:
    return "DELETE", _item_path(params), None, {}


def _item_path(params: dict[str, Any]) -> str:
    item_id = str(params.get("item_id") or "").strip()
    if item_id:
        return f"{DRIVE_ROOT_PREFIX}/items/{quote(item_id, safe='')}"
    file_path = _required(params, "file_path").lstrip("/")
    return f"{DRIVE_ROOT_PREFIX}/root:/{_encode_path(file_path)}:"


def _encode_path(path: str) -> str:
    return "/".join(quote(segment, safe="") for segment in path.split("/"))


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"OneDrive: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_CHILDREN: _build_list_children,
    OP_GET_ITEM: _build_get_item,
    OP_UPLOAD_SMALL: _build_upload_small,
    OP_UPLOAD_LARGE: _build_upload_large,
    OP_DOWNLOAD_ITEM: _build_download_item,
    OP_DELETE_ITEM: _build_delete_item,
}
