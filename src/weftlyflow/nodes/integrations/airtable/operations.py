"""Per-operation request builders for the Airtable node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Table names can contain spaces — callers pass them pre-encoded to
:func:`urllib.parse.quote` so paths survive URL encoding.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.airtable.constants import (
    API_VERSION_PREFIX,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MAX_RECORDS_PER_CREATE,
    OP_CREATE_RECORDS,
    OP_DELETE_RECORD,
    OP_GET_RECORD,
    OP_LIST_RECORDS,
    OP_UPDATE_RECORD,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Airtable: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_records(params: dict[str, Any]) -> RequestSpec:
    path = _table_path(params)
    query: dict[str, Any] = {"pageSize": _coerce_page_size(params.get("page_size"))}
    view = str(params.get("view") or "").strip()
    if view:
        query["view"] = view
    filter_formula = str(params.get("filter_by_formula") or "").strip()
    if filter_formula:
        query["filterByFormula"] = filter_formula
    offset = str(params.get("offset") or "").strip()
    if offset:
        query["offset"] = offset
    max_records = params.get("max_records")
    if max_records not in (None, ""):
        query["maxRecords"] = _coerce_positive_int(max_records, field="max_records")
    return "GET", path, None, query


def _build_get_record(params: dict[str, Any]) -> RequestSpec:
    record_id = _required(params, "record_id")
    path = f"{_table_path(params)}/{quote(record_id, safe='')}"
    return "GET", path, None, {}


def _build_create_records(params: dict[str, Any]) -> RequestSpec:
    records = _coerce_records(params.get("records"))
    body: dict[str, Any] = {"records": records}
    typecast = params.get("typecast")
    if isinstance(typecast, bool):
        body["typecast"] = typecast
    return "POST", _table_path(params), body, {}


def _build_update_record(params: dict[str, Any]) -> RequestSpec:
    record_id = _required(params, "record_id")
    fields = params.get("fields")
    if not isinstance(fields, dict):
        msg = "Airtable: 'fields' must be a JSON object"
        raise ValueError(msg)
    body: dict[str, Any] = {"fields": fields}
    typecast = params.get("typecast")
    if isinstance(typecast, bool):
        body["typecast"] = typecast
    path = f"{_table_path(params)}/{quote(record_id, safe='')}"
    return "PATCH", path, body, {}


def _build_delete_record(params: dict[str, Any]) -> RequestSpec:
    record_id = _required(params, "record_id")
    path = f"{_table_path(params)}/{quote(record_id, safe='')}"
    return "DELETE", path, None, {}


def _table_path(params: dict[str, Any]) -> str:
    base_id = _required(params, "base_id")
    table = _required(params, "table")
    return f"{API_VERSION_PREFIX}/{quote(base_id, safe='')}/{quote(table, safe='')}"


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Airtable: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_records(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        msg = "Airtable: 'records' must contain at least one record"
        raise ValueError(msg)
    if len(raw) > MAX_RECORDS_PER_CREATE:
        msg = f"Airtable: create_records accepts at most {MAX_RECORDS_PER_CREATE} records"
        raise ValueError(msg)
    out: list[dict[str, Any]] = []
    for record in raw:
        if not isinstance(record, dict):
            msg = "Airtable: each record must be an object"
            raise ValueError(msg)
        fields = record.get("fields", record)
        if not isinstance(fields, dict):
            msg = "Airtable: each record's 'fields' must be an object"
            raise ValueError(msg)
        out.append({"fields": fields})
    return out


def _coerce_page_size(raw: Any) -> int:
    if raw is None or raw == "":
        return DEFAULT_PAGE_SIZE
    value = _coerce_positive_int(raw, field="page_size")
    return min(value, MAX_PAGE_SIZE)


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Airtable: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Airtable: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_RECORDS: _build_list_records,
    OP_GET_RECORD: _build_get_record,
    OP_CREATE_RECORDS: _build_create_records,
    OP_UPDATE_RECORD: _build_update_record,
    OP_DELETE_RECORD: _build_delete_record,
}
