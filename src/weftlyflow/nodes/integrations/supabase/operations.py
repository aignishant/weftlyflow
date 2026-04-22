"""Per-operation request builders for the Supabase PostgREST node.

Each builder returns ``(http_method, path, json_body, query_params)``.
PostgREST encodes filters as query parameters with operator prefixes
(e.g. ``id=eq.1``, ``age=gte.18``). This module forwards caller-supplied
filters verbatim and layers on ``select``/``order``/``limit``/``offset``
for read operations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.supabase.constants import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    OP_DELETE,
    OP_INSERT,
    OP_SELECT,
    OP_UPDATE,
    OP_UPSERT,
    REST_VERSION_PREFIX,
)

RequestSpec = tuple[str, str, Any, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Supabase: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_select(params: dict[str, Any]) -> RequestSpec:
    table = _required(params, "table")
    query = _common_filters(params)
    columns = str(params.get("select") or "").strip()
    if columns:
        query["select"] = columns
    order = str(params.get("order") or "").strip()
    if order:
        query["order"] = order
    query["limit"] = _coerce_limit(params.get("limit"))
    offset = params.get("offset")
    if offset not in (None, ""):
        query["offset"] = _coerce_offset(offset)
    return "GET", _table_path(table), None, query


def _build_insert(params: dict[str, Any]) -> RequestSpec:
    table = _required(params, "table")
    rows = _coerce_rows(_rows_from(params))
    query: dict[str, Any] = {}
    return "POST", _table_path(table), rows, query


def _build_update(params: dict[str, Any]) -> RequestSpec:
    table = _required(params, "table")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Supabase: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    query = _common_filters(params)
    if not query:
        msg = "Supabase: update requires at least one 'filters' entry"
        raise ValueError(msg)
    return "PATCH", _table_path(table), dict(fields), query


def _build_delete(params: dict[str, Any]) -> RequestSpec:
    table = _required(params, "table")
    query = _common_filters(params)
    if not query:
        msg = "Supabase: delete requires at least one 'filters' entry"
        raise ValueError(msg)
    return "DELETE", _table_path(table), None, query


def _build_upsert(params: dict[str, Any]) -> RequestSpec:
    table = _required(params, "table")
    rows = _coerce_rows(_rows_from(params))
    on_conflict = str(params.get("on_conflict") or "").strip()
    query: dict[str, Any] = {}
    if on_conflict:
        query["on_conflict"] = on_conflict
    return "POST", _table_path(table), rows, query


def _common_filters(params: dict[str, Any]) -> dict[str, Any]:
    filters = params.get("filters")
    if filters in (None, ""):
        return {}
    if not isinstance(filters, dict):
        msg = "Supabase: 'filters' must be a JSON object of column → operator-value"
        raise ValueError(msg)
    query: dict[str, Any] = {}
    for column, value in filters.items():
        if not isinstance(column, str) or not column:
            msg = f"Supabase: invalid filter column {column!r}"
            raise ValueError(msg)
        if isinstance(value, str):
            query[column] = value
        else:
            query[column] = f"eq.{value}"
    return query


def _rows_from(params: dict[str, Any]) -> Any:
    if "rows" in params and params["rows"] is not None:
        return params["rows"]
    return params.get("row")


def _coerce_rows(raw: Any) -> list[dict[str, Any]] | dict[str, Any]:
    if raw is None:
        msg = "Supabase: 'rows' is required"
        raise ValueError(msg)
    if isinstance(raw, dict):
        if not raw:
            msg = "Supabase: 'rows' must be a non-empty object"
            raise ValueError(msg)
        return raw
    if isinstance(raw, list):
        if not raw:
            msg = "Supabase: 'rows' must be a non-empty list"
            raise ValueError(msg)
        for entry in raw:
            if not isinstance(entry, dict):
                msg = "Supabase: every row must be a JSON object"
                raise ValueError(msg)
        return raw
    msg = "Supabase: 'rows' must be a JSON object or list of objects"
    raise ValueError(msg)


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Supabase: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Supabase: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIMIT)


def _coerce_offset(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Supabase: 'offset' must be an integer"
        raise ValueError(msg) from exc
    if value < 0:
        msg = "Supabase: 'offset' must be >= 0"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Supabase: {key!r} is required"
        raise ValueError(msg)
    return value


def _table_path(table: str) -> str:
    return f"{REST_VERSION_PREFIX}/{quote(table, safe='')}"


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SELECT: _build_select,
    OP_INSERT: _build_insert,
    OP_UPDATE: _build_update,
    OP_DELETE: _build_delete,
    OP_UPSERT: _build_upsert,
}
