"""Per-operation request builders for the PagerDuty REST v2 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
PagerDuty wraps mutating bodies in a single root key (``incident``,
``note``); we produce that envelope here so the node layer can stay
auth-focused.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.pagerduty.constants import (
    DEFAULT_LIST_LIMIT,
    INCIDENT_STATUSES,
    INCIDENT_URGENCIES,
    MAX_LIST_LIMIT,
    OP_ADD_NOTE,
    OP_CREATE_INCIDENT,
    OP_GET_INCIDENT,
    OP_LIST_INCIDENTS,
    OP_UPDATE_INCIDENT,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_UPDATE_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {"status", "priority", "resolution", "escalation_level", "assignments"},
)


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"PagerDuty: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_incidents(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_limit(params.get("limit"))}
    offset = params.get("offset")
    if offset is not None and offset != "":
        try:
            offset_value = int(offset)
        except (TypeError, ValueError) as exc:
            msg = "PagerDuty: 'offset' must be an integer"
            raise ValueError(msg) from exc
        if offset_value < 0:
            msg = "PagerDuty: 'offset' must be >= 0"
            raise ValueError(msg)
        query["offset"] = offset_value
    statuses = _coerce_string_list(params.get("statuses"), field="statuses")
    if statuses:
        for status in statuses:
            if status not in INCIDENT_STATUSES:
                msg = f"PagerDuty: invalid status {status!r}"
                raise ValueError(msg)
        query["statuses[]"] = statuses
    urgencies = _coerce_string_list(params.get("urgencies"), field="urgencies")
    if urgencies:
        for urgency in urgencies:
            if urgency not in INCIDENT_URGENCIES:
                msg = f"PagerDuty: invalid urgency {urgency!r}"
                raise ValueError(msg)
        query["urgencies[]"] = urgencies
    service_ids = _coerce_string_list(params.get("service_ids"), field="service_ids")
    if service_ids:
        query["service_ids[]"] = service_ids
    return "GET", "/incidents", None, query


def _build_get_incident(params: dict[str, Any]) -> RequestSpec:
    incident_id = _required(params, "incident_id")
    return "GET", f"/incidents/{quote(incident_id, safe='')}", None, {}


def _build_create_incident(params: dict[str, Any]) -> RequestSpec:
    title = _required(params, "title")
    service_id = _required(params, "service_id")
    urgency = str(params.get("urgency") or "").strip().lower()
    body_text = str(params.get("body") or "").strip()
    incident: dict[str, Any] = {
        "type": "incident",
        "title": title,
        "service": {"id": service_id, "type": "service_reference"},
    }
    if urgency:
        if urgency not in INCIDENT_URGENCIES:
            msg = f"PagerDuty: invalid urgency {urgency!r}"
            raise ValueError(msg)
        incident["urgency"] = urgency
    if body_text:
        incident["body"] = {"type": "incident_body", "details": body_text}
    return "POST", "/incidents", {"incident": incident}, {}


def _build_update_incident(params: dict[str, Any]) -> RequestSpec:
    incident_id = _required(params, "incident_id")
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "PagerDuty: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    for key in updates:
        if key not in _UPDATE_ALLOWED_FIELDS:
            msg = f"PagerDuty: unknown incident field {key!r}"
            raise ValueError(msg)
    status = updates.get("status")
    if isinstance(status, str) and status not in INCIDENT_STATUSES:
        msg = f"PagerDuty: invalid status {status!r}"
        raise ValueError(msg)
    incident_body: dict[str, Any] = {"type": "incident_reference", **updates}
    path = f"/incidents/{quote(incident_id, safe='')}"
    return "PUT", path, {"incident": incident_body}, {}


def _build_add_note(params: dict[str, Any]) -> RequestSpec:
    incident_id = _required(params, "incident_id")
    content = str(params.get("content") or "")
    if not content.strip():
        msg = "PagerDuty: 'content' is required for add_note"
        raise ValueError(msg)
    path = f"/incidents/{quote(incident_id, safe='')}/notes"
    return "POST", path, {"note": {"content": content}}, {}


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"PagerDuty: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"PagerDuty: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "PagerDuty: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "PagerDuty: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_INCIDENTS: _build_list_incidents,
    OP_GET_INCIDENT: _build_get_incident,
    OP_CREATE_INCIDENT: _build_create_incident,
    OP_UPDATE_INCIDENT: _build_update_incident,
    OP_ADD_NOTE: _build_add_note,
}
