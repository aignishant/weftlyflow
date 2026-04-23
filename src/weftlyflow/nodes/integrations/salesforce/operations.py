"""Per-operation request builders for the Salesforce REST node.

Each builder returns ``(http_method, path, body, query)``. Paths are
prefixed with ``/services/data/<version>`` and the node layer prepends
the per-org ``instance_url`` from the credential.

The listing operation is translated to a SOQL ``SELECT ... FROM <object>``
under the hood — Salesforce does not expose a generic "list records"
endpoint; the common way to page records is SOQL via ``/query``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.salesforce.constants import (
    DEFAULT_API_VERSION,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    OP_CREATE_RECORD,
    OP_DELETE_RECORD,
    OP_GET_RECORD,
    OP_LIST_RECORDS,
    OP_QUERY,
    OP_UPDATE_RECORD,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_ALLOWED_ID_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
)


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Salesforce: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _base_prefix(params: dict[str, Any]) -> str:
    version = str(params.get("api_version") or "").strip() or DEFAULT_API_VERSION
    _validate_version(version)
    return f"/services/data/{version}"


def _build_list_records(params: dict[str, Any]) -> RequestSpec:
    sobject = _validated_sobject(params)
    fields = _coerce_string_list(params.get("fields"), field="fields")
    if not fields:
        fields = ["Id", "Name"]
    where = str(params.get("where") or "").strip()
    order_by = str(params.get("order_by") or "").strip()
    limit = _coerce_limit(params.get("limit"))
    select_list = ", ".join(fields)
    soql = f"SELECT {select_list} FROM {sobject}"
    if where:
        soql += f" WHERE {where}"
    if order_by:
        soql += f" ORDER BY {order_by}"
    soql += f" LIMIT {limit}"
    path = f"{_base_prefix(params)}/query"
    return "GET", path, None, {"q": soql}


def _build_get_record(params: dict[str, Any]) -> RequestSpec:
    sobject = _validated_sobject(params)
    record_id = _required(params, "record_id")
    path = f"{_base_prefix(params)}/sobjects/{sobject}/{quote(record_id, safe='')}"
    fields = _coerce_string_list(params.get("fields"), field="fields")
    query: dict[str, Any] = {}
    if fields:
        query["fields"] = ",".join(fields)
    return "GET", path, None, query


def _build_create_record(params: dict[str, Any]) -> RequestSpec:
    sobject = _validated_sobject(params)
    document = params.get("document")
    if not isinstance(document, dict) or not document:
        msg = "Salesforce: 'document' must be a non-empty JSON object"
        raise ValueError(msg)
    path = f"{_base_prefix(params)}/sobjects/{sobject}"
    return "POST", path, dict(document), {}


def _build_update_record(params: dict[str, Any]) -> RequestSpec:
    sobject = _validated_sobject(params)
    record_id = _required(params, "record_id")
    document = params.get("document")
    if not isinstance(document, dict) or not document:
        msg = "Salesforce: 'document' must be a non-empty JSON object"
        raise ValueError(msg)
    path = f"{_base_prefix(params)}/sobjects/{sobject}/{quote(record_id, safe='')}"
    return "PATCH", path, dict(document), {}


def _build_delete_record(params: dict[str, Any]) -> RequestSpec:
    sobject = _validated_sobject(params)
    record_id = _required(params, "record_id")
    path = f"{_base_prefix(params)}/sobjects/{sobject}/{quote(record_id, safe='')}"
    return "DELETE", path, None, {}


def _build_query(params: dict[str, Any]) -> RequestSpec:
    soql = _required(params, "soql")
    path = f"{_base_prefix(params)}/query"
    return "GET", path, None, {"q": soql}


def _validated_sobject(params: dict[str, Any]) -> str:
    value = _required(params, "sobject")
    if not all(ch in _ALLOWED_ID_CHARS for ch in value):
        msg = "Salesforce: 'sobject' must be alphanumeric/underscore only"
        raise ValueError(msg)
    return value


def _validate_version(value: str) -> None:
    if not value.startswith("v") or not value[1:].replace(".", "").isdigit():
        msg = f"Salesforce: 'api_version' must look like 'v58.0', got {value!r}"
        raise ValueError(msg)


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Salesforce: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Salesforce: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Salesforce: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Salesforce: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_RECORDS: _build_list_records,
    OP_GET_RECORD: _build_get_record,
    OP_CREATE_RECORD: _build_create_record,
    OP_UPDATE_RECORD: _build_update_record,
    OP_DELETE_RECORD: _build_delete_record,
    OP_QUERY: _build_query,
}
