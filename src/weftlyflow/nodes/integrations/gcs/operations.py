"""Per-operation request builders for the Google Cloud Storage node.

Each builder returns ``(http_method, path, query)``. Paths are
relative to ``https://storage.googleapis.com`` and use the JSON API
namespace (``/storage/v1/...``). Object names must be URL-quoted
because GCS permits ``/`` and other special characters inside a
single object path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.gcs.constants import (
    OP_DELETE_OBJECT,
    OP_GET_OBJECT,
    OP_LIST_BUCKETS,
    OP_LIST_OBJECTS,
)

RequestSpec = tuple[str, str, dict[str, str]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"GCS: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_buckets(params: dict[str, Any]) -> RequestSpec:
    project = _required_str(params, "project")
    query: dict[str, str] = {"project": project}
    page_token = str(params.get("page_token") or "").strip()
    if page_token:
        query["pageToken"] = page_token
    prefix = str(params.get("prefix") or "").strip()
    if prefix:
        query["prefix"] = prefix
    return "GET", "/storage/v1/b", query


def _build_list_objects(params: dict[str, Any]) -> RequestSpec:
    bucket = _required_str(params, "bucket")
    query: dict[str, str] = {}
    prefix = str(params.get("prefix") or "").strip()
    if prefix:
        query["prefix"] = prefix
    page_token = str(params.get("page_token") or "").strip()
    if page_token:
        query["pageToken"] = page_token
    delimiter = str(params.get("delimiter") or "").strip()
    if delimiter:
        query["delimiter"] = delimiter
    return "GET", f"/storage/v1/b/{quote(bucket, safe='')}/o", query


def _build_get_object(params: dict[str, Any]) -> RequestSpec:
    bucket = _required_str(params, "bucket")
    object_name = _required_str(params, "object_name")
    query: dict[str, str] = {}
    alt = str(params.get("alt") or "").strip()
    if alt:
        query["alt"] = alt
    return (
        "GET",
        f"/storage/v1/b/{quote(bucket, safe='')}/o/{quote(object_name, safe='')}",
        query,
    )


def _build_delete_object(params: dict[str, Any]) -> RequestSpec:
    bucket = _required_str(params, "bucket")
    object_name = _required_str(params, "object_name")
    return (
        "DELETE",
        f"/storage/v1/b/{quote(bucket, safe='')}/o/{quote(object_name, safe='')}",
        {},
    )


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"GCS: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_BUCKETS: _build_list_buckets,
    OP_LIST_OBJECTS: _build_list_objects,
    OP_GET_OBJECT: _build_get_object,
    OP_DELETE_OBJECT: _build_delete_object,
}
