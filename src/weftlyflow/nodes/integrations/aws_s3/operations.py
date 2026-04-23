"""Per-operation request builders for the AWS S3 node.

Each builder returns ``(http_method, path, query, extra_headers,
bucket)``. The ``bucket`` field drives the virtual-host endpoint
(``<bucket>.s3.<region>.amazonaws.com``); ``list_buckets`` returns an
empty bucket so the node falls back to the regional service host.

S3 path quirks:

* Keys are not percent-encoded in the canonical path form; the SigV4
  signer handles the encoding uniformly.
* ``list_objects`` uses the ``list-type=2`` query flag for ListObjectsV2.
* ``copy_object`` places the *source* in the ``x-amz-copy-source``
  header and targets the *destination* in the request path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.aws_s3.constants import (
    DEFAULT_MAX_KEYS,
    MAX_MAX_KEYS,
    OP_COPY_OBJECT,
    OP_DELETE_OBJECT,
    OP_GET_OBJECT,
    OP_HEAD_OBJECT,
    OP_LIST_BUCKETS,
    OP_LIST_OBJECTS,
)

RequestSpec = tuple[str, str, dict[str, Any], dict[str, str], str]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"AWS S3: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_buckets(params: dict[str, Any]) -> RequestSpec:
    del params
    return "GET", "/", {}, {}, ""


def _build_list_objects(params: dict[str, Any]) -> RequestSpec:
    bucket = _required(params, "bucket")
    query: dict[str, Any] = {
        "list-type": "2",
        "max-keys": str(_coerce_max_keys(params.get("max_keys"))),
    }
    prefix = str(params.get("prefix") or "").strip()
    if prefix:
        query["prefix"] = prefix
    delimiter = str(params.get("delimiter") or "").strip()
    if delimiter:
        query["delimiter"] = delimiter
    continuation = str(params.get("continuation_token") or "").strip()
    if continuation:
        query["continuation-token"] = continuation
    return "GET", "/", query, {}, bucket


def _build_head_object(params: dict[str, Any]) -> RequestSpec:
    bucket = _required(params, "bucket")
    key = _required(params, "key")
    return "HEAD", _object_path(key), {}, {}, bucket


def _build_get_object(params: dict[str, Any]) -> RequestSpec:
    bucket = _required(params, "bucket")
    key = _required(params, "key")
    return "GET", _object_path(key), {}, {}, bucket


def _build_delete_object(params: dict[str, Any]) -> RequestSpec:
    bucket = _required(params, "bucket")
    key = _required(params, "key")
    return "DELETE", _object_path(key), {}, {}, bucket


def _build_copy_object(params: dict[str, Any]) -> RequestSpec:
    bucket = _required(params, "bucket")
    key = _required(params, "key")
    source_bucket = _required(params, "source_bucket")
    source_key = _required(params, "source_key")
    headers = {
        "x-amz-copy-source": f"/{source_bucket}/{source_key.lstrip('/')}",
    }
    return "PUT", _object_path(key), {}, headers, bucket


def _object_path(key: str) -> str:
    return "/" + key.lstrip("/")


def _coerce_max_keys(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_MAX_KEYS
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "AWS S3: 'max_keys' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "AWS S3: 'max_keys' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_MAX_KEYS)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"AWS S3: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_BUCKETS: _build_list_buckets,
    OP_LIST_OBJECTS: _build_list_objects,
    OP_HEAD_OBJECT: _build_head_object,
    OP_GET_OBJECT: _build_get_object,
    OP_DELETE_OBJECT: _build_delete_object,
    OP_COPY_OBJECT: _build_copy_object,
}
