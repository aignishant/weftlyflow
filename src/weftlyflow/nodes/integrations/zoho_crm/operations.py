"""Per-operation request builders for the Zoho CRM v6 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Zoho wraps every create/update/delete body in a top-level ``data``
array, and emits its own ``data`` array in paginated responses — this
module handles the envelope so the node layer stays auth-focused.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.zoho_crm.constants import (
    API_VERSION_PREFIX,
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    OP_CREATE_RECORD,
    OP_DELETE_RECORD,
    OP_GET_RECORD,
    OP_LIST_RECORDS,
    OP_SEARCH_RECORDS,
    OP_UPDATE_RECORD,
    SEARCH_CRITERIA_KEYS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Zoho: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_records(params: dict[str, Any]) -> RequestSpec:
    module = _required(params, "module")
    query: dict[str, Any] = {"per_page": _coerce_per_page(params.get("per_page"))}
    page_value = _coerce_page(params.get("page"))
    if page_value is not None:
        query["page"] = page_value
    fields = _coerce_string_list(params.get("fields"), field="fields")
    if fields:
        query["fields"] = ",".join(fields)
    sort_by = str(params.get("sort_by") or "").strip()
    if sort_by:
        query["sort_by"] = sort_by
    sort_order = str(params.get("sort_order") or "").strip().lower()
    if sort_order:
        if sort_order not in {"asc", "desc"}:
            msg = f"Zoho: invalid sort_order {sort_order!r}"
            raise ValueError(msg)
        query["sort_order"] = sort_order
    return "GET", f"{API_VERSION_PREFIX}/{quote(module, safe='')}", None, query


def _build_get_record(params: dict[str, Any]) -> RequestSpec:
    module = _required(params, "module")
    record_id = _required(params, "record_id")
    path = (
        f"{API_VERSION_PREFIX}/{quote(module, safe='')}"
        f"/{quote(record_id, safe='')}"
    )
    return "GET", path, None, {}


def _build_create_record(params: dict[str, Any]) -> RequestSpec:
    module = _required(params, "module")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Zoho: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    body: dict[str, Any] = {"data": [dict(fields)]}
    trigger = _coerce_string_list(params.get("trigger"), field="trigger")
    if trigger:
        body["trigger"] = trigger
    return "POST", f"{API_VERSION_PREFIX}/{quote(module, safe='')}", body, {}


def _build_update_record(params: dict[str, Any]) -> RequestSpec:
    module = _required(params, "module")
    record_id = _required(params, "record_id")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Zoho: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    body: dict[str, Any] = {"data": [{**fields, "id": record_id}]}
    path = (
        f"{API_VERSION_PREFIX}/{quote(module, safe='')}"
        f"/{quote(record_id, safe='')}"
    )
    return "PUT", path, body, {}


def _build_delete_record(params: dict[str, Any]) -> RequestSpec:
    module = _required(params, "module")
    record_id = _required(params, "record_id")
    path = (
        f"{API_VERSION_PREFIX}/{quote(module, safe='')}"
        f"/{quote(record_id, safe='')}"
    )
    return "DELETE", path, None, {}


def _build_search_records(params: dict[str, Any]) -> RequestSpec:
    module = _required(params, "module")
    query: dict[str, Any] = {}
    matched = [key for key in SEARCH_CRITERIA_KEYS if str(params.get(key) or "").strip()]
    if not matched:
        msg = (
            "Zoho: search requires one of 'criteria', 'email', 'phone', or 'word'"
        )
        raise ValueError(msg)
    if len(matched) > 1:
        msg = f"Zoho: pick only one search key; got {matched!r}"
        raise ValueError(msg)
    key = matched[0]
    query[key] = str(params[key]).strip()
    query["per_page"] = _coerce_per_page(params.get("per_page"))
    page_value = _coerce_page(params.get("page"))
    if page_value is not None:
        query["page"] = page_value
    path = f"{API_VERSION_PREFIX}/{quote(module, safe='')}/search"
    return "GET", path, None, query


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Zoho: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Zoho: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_page(raw: Any) -> int | None:
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Zoho: 'page' must be an integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Zoho: 'page' must be >= 1"
        raise ValueError(msg)
    return value


def _coerce_per_page(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PER_PAGE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Zoho: 'per_page' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Zoho: 'per_page' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PER_PAGE)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_RECORDS: _build_list_records,
    OP_GET_RECORD: _build_get_record,
    OP_CREATE_RECORD: _build_create_record,
    OP_UPDATE_RECORD: _build_update_record,
    OP_DELETE_RECORD: _build_delete_record,
    OP_SEARCH_RECORDS: _build_search_records,
}
