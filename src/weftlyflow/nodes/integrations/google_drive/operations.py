"""Per-operation request builders for the Google Drive node.

Each builder returns ``(http_method, path, body_bytes, query, content_type)``
where ``body_bytes`` is the pre-serialized request body (bytes for the
multipart upload, ``None`` for read/delete ops, and a ``dict`` for
JSON ops which the dispatcher serializes with ``json=``).

Distinctive Drive shape:

* **Resumable is handled by the simpler ``multipart`` variant here.**
  ``upload_file`` hits
  ``/upload/drive/v3/files?uploadType=multipart`` with
  ``Content-Type: multipart/related; boundary=<...>`` and **two** parts:
  a JSON metadata part (``{"name": ..., "parents": ...}``) followed by
  the raw file bytes — boundary-delimited. No other Google API in the
  catalog uses this envelope.
* Folders are just files with the distinguished mime-type
  ``application/vnd.google-apps.folder`` and no payload, so
  ``create_folder`` reuses ``POST /files`` with a JSON body.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.google_drive.constants import (
    DRIVE_API_PREFIX,
    DRIVE_UPLOAD_PREFIX,
    MULTIPART_BOUNDARY,
    OP_CREATE_FOLDER,
    OP_DELETE_FILE,
    OP_DOWNLOAD_FILE,
    OP_GET_FILE,
    OP_LIST_FILES,
    OP_UPLOAD_FILE,
)

RequestSpec = tuple[str, str, Any, dict[str, Any], str | None]
_FOLDER_MIME_TYPE: str = "application/vnd.google-apps.folder"


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Google Drive: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_files(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    for key in ("q", "pageSize", "pageToken", "orderBy", "spaces", "fields"):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = _stringify(value)
    return "GET", f"{DRIVE_API_PREFIX}/files", None, query, None


def _build_get_file(params: dict[str, Any]) -> RequestSpec:
    file_id = _required(params, "file_id")
    query: dict[str, Any] = {}
    fields = str(params.get("fields") or "").strip()
    if fields:
        query["fields"] = fields
    path = f"{DRIVE_API_PREFIX}/files/{quote(file_id, safe='')}"
    return "GET", path, None, query, None


def _build_create_folder(params: dict[str, Any]) -> RequestSpec:
    name = _required(params, "name")
    body: dict[str, Any] = {"name": name, "mimeType": _FOLDER_MIME_TYPE}
    parents = params.get("parents")
    if isinstance(parents, list) and parents:
        body["parents"] = [str(value) for value in parents]
    return "POST", f"{DRIVE_API_PREFIX}/files", body, {}, None


def _build_upload_file(params: dict[str, Any]) -> RequestSpec:
    name = _required(params, "name")
    content_b64 = _required(params, "content_base64")
    try:
        content_bytes = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        msg = "Google Drive: 'content_base64' is not valid base64"
        raise ValueError(msg) from exc
    metadata: dict[str, Any] = {"name": name}
    mime_type = str(params.get("mime_type") or "").strip()
    if mime_type:
        metadata["mimeType"] = mime_type
    parents = params.get("parents")
    if isinstance(parents, list) and parents:
        metadata["parents"] = [str(value) for value in parents]
    payload_mime = mime_type or "application/octet-stream"
    body = _build_multipart_related(metadata, content_bytes, payload_mime)
    content_type = f"multipart/related; boundary={MULTIPART_BOUNDARY}"
    query: dict[str, Any] = {"uploadType": "multipart"}
    return "POST", f"{DRIVE_UPLOAD_PREFIX}/files", body, query, content_type


def _build_download_file(params: dict[str, Any]) -> RequestSpec:
    file_id = _required(params, "file_id")
    path = f"{DRIVE_API_PREFIX}/files/{quote(file_id, safe='')}"
    return "GET", path, None, {"alt": "media"}, None


def _build_delete_file(params: dict[str, Any]) -> RequestSpec:
    file_id = _required(params, "file_id")
    path = f"{DRIVE_API_PREFIX}/files/{quote(file_id, safe='')}"
    return "DELETE", path, None, {}, None


def _build_multipart_related(
    metadata: dict[str, Any],
    content: bytes,
    content_mime: str,
) -> bytes:
    boundary = MULTIPART_BOUNDARY.encode("ascii")
    metadata_json = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    return (
        b"--"
        + boundary
        + b"\r\n"
        + b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + metadata_json
        + b"\r\n--"
        + boundary
        + b"\r\n"
        + f"Content-Type: {content_mime}\r\n\r\n".encode("ascii")
        + content
        + b"\r\n--"
        + boundary
        + b"--\r\n"
    )


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Google Drive: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_FILES: _build_list_files,
    OP_GET_FILE: _build_get_file,
    OP_CREATE_FOLDER: _build_create_folder,
    OP_UPLOAD_FILE: _build_upload_file,
    OP_DOWNLOAD_FILE: _build_download_file,
    OP_DELETE_FILE: _build_delete_file,
}
