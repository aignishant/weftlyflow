"""Per-operation request builders for the Backblaze B2 node.

Each builder returns ``(path, json_body)``. B2 uses POST for every
Native API call — the ``path`` is relative to the per-session
``apiUrl`` returned by ``b2_authorize_account`` and the ``json_body``
is the operation-specific payload.

Account-scoped operations (``list_buckets``) require the session's
``accountId``; the node injects it before handing params to the
builder so builder signatures stay uniform.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.backblaze_b2.constants import (
    DEFAULT_MAX_FILE_COUNT,
    MAX_FILE_COUNT,
    OP_DELETE_FILE_VERSION,
    OP_GET_UPLOAD_URL,
    OP_LIST_BUCKETS,
    OP_LIST_FILE_NAMES,
)

RequestSpec = tuple[str, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Backblaze B2: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_buckets(params: dict[str, Any]) -> RequestSpec:
    account_id = _required(params, "account_id")
    body: dict[str, Any] = {"accountId": account_id}
    bucket_id = str(params.get("bucket_id") or "").strip()
    if bucket_id:
        body["bucketId"] = bucket_id
    bucket_name = str(params.get("bucket") or "").strip()
    if bucket_name:
        body["bucketName"] = bucket_name
    return "/b2api/v3/b2_list_buckets", body


def _build_list_file_names(params: dict[str, Any]) -> RequestSpec:
    bucket_id = _required(params, "bucket_id")
    body: dict[str, Any] = {
        "bucketId": bucket_id,
        "maxFileCount": _coerce_max_file_count(params.get("max_file_count")),
    }
    prefix = str(params.get("prefix") or "").strip()
    if prefix:
        body["prefix"] = prefix
    start_file_name = str(params.get("start_file_name") or "").strip()
    if start_file_name:
        body["startFileName"] = start_file_name
    delimiter = str(params.get("delimiter") or "").strip()
    if delimiter:
        body["delimiter"] = delimiter
    return "/b2api/v3/b2_list_file_names", body


def _build_get_upload_url(params: dict[str, Any]) -> RequestSpec:
    bucket_id = _required(params, "bucket_id")
    return "/b2api/v3/b2_get_upload_url", {"bucketId": bucket_id}


def _build_delete_file_version(params: dict[str, Any]) -> RequestSpec:
    file_id = _required(params, "file_id")
    file_name = _required(params, "file_name")
    return (
        "/b2api/v3/b2_delete_file_version",
        {"fileId": file_id, "fileName": file_name},
    )


def _coerce_max_file_count(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_MAX_FILE_COUNT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Backblaze B2: 'max_file_count' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Backblaze B2: 'max_file_count' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_FILE_COUNT)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Backblaze B2: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_BUCKETS: _build_list_buckets,
    OP_LIST_FILE_NAMES: _build_list_file_names,
    OP_GET_UPLOAD_URL: _build_get_upload_url,
    OP_DELETE_FILE_VERSION: _build_delete_file_version,
}
