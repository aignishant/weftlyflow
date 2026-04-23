"""Per-operation request builders for the Azure Blob Storage node.

Each builder returns ``(method, path, query, extra_headers, body)``.
Paths are relative to ``https://<account>.blob.core.windows.net``;
the SharedKey injector pre-pends the account segment when it builds
the canonical resource.

Blob path quirks:

* Container list uses the service root with ``comp=list`` and
  ``restype=service``; per Azure spec both are required.
* Blob list scopes the container with ``restype=container`` +
  ``comp=list``.
* ``put_blob`` attaches the ``x-ms-blob-type: BlockBlob`` header and
  carries the body payload — other blob types (append, page) are out
  of scope for the MVP.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.azure_blob.constants import (
    BLOB_TYPE_BLOCK,
    OP_DELETE_BLOB,
    OP_GET_BLOB,
    OP_LIST_BLOBS,
    OP_LIST_CONTAINERS,
    OP_PUT_BLOB,
)

RequestSpec = tuple[str, str, dict[str, str], dict[str, str], bytes]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Azure Blob: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_containers(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, str] = {"comp": "list"}
    prefix = str(params.get("prefix") or "").strip()
    if prefix:
        query["prefix"] = prefix
    marker = str(params.get("marker") or "").strip()
    if marker:
        query["marker"] = marker
    return "GET", "/", query, {}, b""


def _build_list_blobs(params: dict[str, Any]) -> RequestSpec:
    container = _required(params, "container")
    query: dict[str, str] = {"restype": "container", "comp": "list"}
    prefix = str(params.get("prefix") or "").strip()
    if prefix:
        query["prefix"] = prefix
    marker = str(params.get("marker") or "").strip()
    if marker:
        query["marker"] = marker
    delimiter = str(params.get("delimiter") or "").strip()
    if delimiter:
        query["delimiter"] = delimiter
    return "GET", f"/{quote(container, safe='')}", query, {}, b""


def _build_get_blob(params: dict[str, Any]) -> RequestSpec:
    container = _required(params, "container")
    blob = _required(params, "blob")
    return "GET", _blob_path(container, blob), {}, {}, b""


def _build_put_blob(params: dict[str, Any]) -> RequestSpec:
    container = _required(params, "container")
    blob = _required(params, "blob")
    raw_body = params.get("body")
    if isinstance(raw_body, str):
        body = raw_body.encode("utf-8")
    elif isinstance(raw_body, bytes):
        body = raw_body
    elif raw_body is None:
        body = b""
    else:
        msg = "Azure Blob: 'body' must be str or bytes"
        raise ValueError(msg)
    content_type = str(params.get("content_type") or "application/octet-stream").strip()
    headers: dict[str, str] = {
        "x-ms-blob-type": BLOB_TYPE_BLOCK,
        "Content-Type": content_type or "application/octet-stream",
        "Content-Length": str(len(body)),
    }
    return "PUT", _blob_path(container, blob), {}, headers, body


def _build_delete_blob(params: dict[str, Any]) -> RequestSpec:
    container = _required(params, "container")
    blob = _required(params, "blob")
    return "DELETE", _blob_path(container, blob), {}, {}, b""


def _blob_path(container: str, blob: str) -> str:
    return f"/{quote(container, safe='')}/{quote(blob, safe='')}"


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Azure Blob: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_CONTAINERS: _build_list_containers,
    OP_LIST_BLOBS: _build_list_blobs,
    OP_GET_BLOB: _build_get_blob,
    OP_PUT_BLOB: _build_put_blob,
    OP_DELETE_BLOB: _build_delete_blob,
}
