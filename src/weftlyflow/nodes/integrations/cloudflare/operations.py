"""Per-operation request builders for the Cloudflare client/v4 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Paths are prefixed with ``/`` and the node layer prepends the shared
``https://api.cloudflare.com/client/v4`` base URL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.cloudflare.constants import (
    DEFAULT_PER_PAGE,
    DNS_RECORD_TYPES,
    DNS_RECORD_UPDATE_FIELDS,
    MAX_PER_PAGE,
    MIN_TTL_SECONDS,
    OP_CREATE_DNS_RECORD,
    OP_DELETE_DNS_RECORD,
    OP_GET_ZONE,
    OP_LIST_DNS_RECORDS,
    OP_LIST_ZONES,
    OP_UPDATE_DNS_RECORD,
    TTL_AUTO,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Cloudflare: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_zones(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"per_page": _coerce_per_page(params.get("per_page"))}
    name = str(params.get("name") or "").strip()
    if name:
        query["name"] = name
    status = str(params.get("status") or "").strip().lower()
    if status:
        query["status"] = status
    page = _coerce_page(params.get("page"))
    if page is not None:
        query["page"] = page
    return "GET", "/zones", None, query


def _build_get_zone(params: dict[str, Any]) -> RequestSpec:
    zone_id = _required(params, "zone_id")
    return "GET", f"/zones/{quote(zone_id, safe='')}", None, {}


def _build_list_dns_records(params: dict[str, Any]) -> RequestSpec:
    zone_id = _required(params, "zone_id")
    query: dict[str, Any] = {"per_page": _coerce_per_page(params.get("per_page"))}
    record_type = str(params.get("type") or "").strip().upper()
    if record_type:
        _require_record_type(record_type)
        query["type"] = record_type
    name = str(params.get("name") or "").strip()
    if name:
        query["name"] = name
    page = _coerce_page(params.get("page"))
    if page is not None:
        query["page"] = page
    path = f"/zones/{quote(zone_id, safe='')}/dns_records"
    return "GET", path, None, query


def _build_create_dns_record(params: dict[str, Any]) -> RequestSpec:
    zone_id = _required(params, "zone_id")
    record_type = _required(params, "type").upper()
    _require_record_type(record_type)
    name = _required(params, "name")
    content = _required(params, "content")
    body: dict[str, Any] = {"type": record_type, "name": name, "content": content}
    ttl = params.get("ttl")
    if ttl not in (None, ""):
        body["ttl"] = _coerce_ttl(ttl)
    proxied = params.get("proxied")
    if proxied is not None:
        body["proxied"] = bool(proxied)
    priority = params.get("priority")
    if priority not in (None, ""):
        body["priority"] = _coerce_priority(priority)
    path = f"/zones/{quote(zone_id, safe='')}/dns_records"
    return "POST", path, body, {}


def _build_update_dns_record(params: dict[str, Any]) -> RequestSpec:
    zone_id = _required(params, "zone_id")
    record_id = _required(params, "record_id")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Cloudflare: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    unknown = [k for k in fields if k not in DNS_RECORD_UPDATE_FIELDS]
    if unknown:
        msg = f"Cloudflare: unknown dns record field(s) {unknown!r}"
        raise ValueError(msg)
    body = dict(fields)
    if "type" in body:
        body["type"] = str(body["type"]).upper()
        _require_record_type(body["type"])
    path = (
        f"/zones/{quote(zone_id, safe='')}/dns_records"
        f"/{quote(record_id, safe='')}"
    )
    return "PATCH", path, body, {}


def _build_delete_dns_record(params: dict[str, Any]) -> RequestSpec:
    zone_id = _required(params, "zone_id")
    record_id = _required(params, "record_id")
    path = (
        f"/zones/{quote(zone_id, safe='')}/dns_records"
        f"/{quote(record_id, safe='')}"
    )
    return "DELETE", path, None, {}


def _require_record_type(record_type: str) -> None:
    if record_type not in DNS_RECORD_TYPES:
        msg = f"Cloudflare: invalid dns record type {record_type!r}"
        raise ValueError(msg)


def _coerce_ttl(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Cloudflare: 'ttl' must be an integer"
        raise ValueError(msg) from exc
    if value != TTL_AUTO and value < MIN_TTL_SECONDS:
        msg = "Cloudflare: 'ttl' must be 1 (auto) or >= 60 seconds"
        raise ValueError(msg)
    return value


def _coerce_priority(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Cloudflare: 'priority' must be an integer"
        raise ValueError(msg) from exc
    if value < 0:
        msg = "Cloudflare: 'priority' must be >= 0"
        raise ValueError(msg)
    return value


def _coerce_per_page(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PER_PAGE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Cloudflare: 'per_page' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Cloudflare: 'per_page' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PER_PAGE)


def _coerce_page(raw: Any) -> int | None:
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Cloudflare: 'page' must be an integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Cloudflare: 'page' must be >= 1"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Cloudflare: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_ZONES: _build_list_zones,
    OP_GET_ZONE: _build_get_zone,
    OP_LIST_DNS_RECORDS: _build_list_dns_records,
    OP_CREATE_DNS_RECORD: _build_create_dns_record,
    OP_UPDATE_DNS_RECORD: _build_update_dns_record,
    OP_DELETE_DNS_RECORD: _build_delete_dns_record,
}
