"""Per-operation request builders for the NetSuite node.

Each builder returns ``(http_method, path, body, query, extra_headers)``.
Paths are relative to the account host (SuiteTalk REST root).

Distinctive NetSuite shapes:

* SuiteQL requires ``Prefer: transient`` and carries the query in a
  JSON body ``{"q": "..."}``; offset/limit are query parameters.
* Record endpoints use REST paths under ``/services/rest/record/v1/<type>``
  with ``DELETE`` and ``GET`` taking the record id in the path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.netsuite.constants import (
    OP_RECORD_CREATE,
    OP_RECORD_DELETE,
    OP_RECORD_GET,
    OP_SUITEQL_QUERY,
    RECORD_PATH,
    SUITEQL_HEADER,
    SUITEQL_HEADER_VALUE,
    SUITEQL_PATH,
)

RequestSpec = tuple[
    str,
    str,
    dict[str, Any] | None,
    dict[str, Any],
    dict[str, str],
]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"NetSuite: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_suiteql_query(params: dict[str, Any]) -> RequestSpec:
    query_sql = _required(params, "query")
    body = {"q": query_sql}
    qs: dict[str, Any] = {}
    limit = params.get("limit")
    if limit is not None and limit != "":
        qs["limit"] = _coerce_positive_int(limit, field="limit")
    offset = params.get("offset")
    if offset is not None and offset != "":
        qs["offset"] = _coerce_non_negative_int(offset, field="offset")
    headers = {SUITEQL_HEADER: SUITEQL_HEADER_VALUE}
    return "POST", SUITEQL_PATH, body, qs, headers


def _build_record_get(params: dict[str, Any]) -> RequestSpec:
    record_type = _required(params, "record_type")
    record_id = _required(params, "record_id")
    path = f"{RECORD_PATH}/{quote(record_type, safe='')}/{quote(record_id, safe='')}"
    return "GET", path, None, {}, {}


def _build_record_create(params: dict[str, Any]) -> RequestSpec:
    record_type = _required(params, "record_type")
    document = _coerce_document(params.get("document"))
    path = f"{RECORD_PATH}/{quote(record_type, safe='')}"
    return "POST", path, document, {}, {}


def _build_record_delete(params: dict[str, Any]) -> RequestSpec:
    record_type = _required(params, "record_type")
    record_id = _required(params, "record_id")
    path = f"{RECORD_PATH}/{quote(record_type, safe='')}/{quote(record_id, safe='')}"
    return "DELETE", path, None, {}, {}


def _coerce_document(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        msg = "NetSuite: 'document' is required"
        raise ValueError(msg)
    if not isinstance(raw, dict):
        msg = "NetSuite: 'document' must be a JSON object"
        raise ValueError(msg)
    return raw


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"NetSuite: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"NetSuite: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _coerce_non_negative_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"NetSuite: {field!r} must be a non-negative integer"
        raise ValueError(msg) from exc
    if value < 0:
        msg = f"NetSuite: {field!r} must be >= 0"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"NetSuite: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SUITEQL_QUERY: _build_suiteql_query,
    OP_RECORD_GET: _build_record_get,
    OP_RECORD_CREATE: _build_record_create,
    OP_RECORD_DELETE: _build_record_delete,
}
