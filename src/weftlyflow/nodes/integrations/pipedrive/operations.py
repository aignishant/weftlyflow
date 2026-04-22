"""Per-operation request builders for the Pipedrive v1 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
The node layer appends the ``api_token`` query parameter separately so
builders focus purely on payload shape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.pipedrive.constants import (
    DEAL_STATUSES,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    OP_CREATE_ACTIVITY,
    OP_CREATE_DEAL,
    OP_CREATE_PERSON,
    OP_GET_DEAL,
    OP_LIST_DEALS,
    OP_UPDATE_DEAL,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_DEAL_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "value",
        "currency",
        "status",
        "stage_id",
        "user_id",
        "person_id",
        "org_id",
        "expected_close_date",
        "probability",
        "lost_reason",
    },
)


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Pipedrive: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_deals(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_limit(params.get("limit"))}
    start = params.get("start")
    if start is not None and start != "":
        try:
            start_value = int(start)
        except (TypeError, ValueError) as exc:
            msg = "Pipedrive: 'start' must be an integer"
            raise ValueError(msg) from exc
        if start_value < 0:
            msg = "Pipedrive: 'start' must be >= 0"
            raise ValueError(msg)
        query["start"] = start_value
    status = str(params.get("status") or "").strip().lower()
    if status:
        if status not in DEAL_STATUSES:
            msg = f"Pipedrive: invalid deal status {status!r}"
            raise ValueError(msg)
        query["status"] = status
    owner_id = params.get("owner_id")
    if owner_id not in (None, ""):
        query["owned_by_you"] = 0
        query["user_id"] = _coerce_int(owner_id, field="owner_id")
    return "GET", "/deals", None, query


def _build_get_deal(params: dict[str, Any]) -> RequestSpec:
    deal_id = _coerce_int(_required(params, "deal_id"), field="deal_id")
    return "GET", f"/deals/{quote(str(deal_id), safe='')}", None, {}


def _build_create_deal(params: dict[str, Any]) -> RequestSpec:
    title = _required(params, "title")
    body: dict[str, Any] = {"title": title}
    value = params.get("value")
    if value not in (None, ""):
        body["value"] = value
    currency = str(params.get("currency") or "").strip()
    if currency:
        body["currency"] = currency
    status = str(params.get("status") or "").strip().lower()
    if status:
        if status not in DEAL_STATUSES:
            msg = f"Pipedrive: invalid deal status {status!r}"
            raise ValueError(msg)
        body["status"] = status
    for optional in ("person_id", "org_id", "stage_id", "user_id"):
        raw = params.get(optional)
        if raw not in (None, ""):
            body[optional] = _coerce_int(raw, field=optional)
    return "POST", "/deals", body, {}


def _build_update_deal(params: dict[str, Any]) -> RequestSpec:
    deal_id = _coerce_int(_required(params, "deal_id"), field="deal_id")
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "Pipedrive: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    for key in updates:
        if key not in _DEAL_UPDATE_FIELDS:
            msg = f"Pipedrive: unknown deal field {key!r}"
            raise ValueError(msg)
    status_update = updates.get("status")
    if isinstance(status_update, str) and status_update.lower() not in DEAL_STATUSES:
        msg = f"Pipedrive: invalid deal status {status_update!r}"
        raise ValueError(msg)
    return "PUT", f"/deals/{quote(str(deal_id), safe='')}", dict(updates), {}


def _build_create_person(params: dict[str, Any]) -> RequestSpec:
    name = _required(params, "name")
    body: dict[str, Any] = {"name": name}
    emails = _coerce_string_list(params.get("emails"), field="emails")
    if emails:
        body["email"] = emails
    phones = _coerce_string_list(params.get("phones"), field="phones")
    if phones:
        body["phone"] = phones
    for optional in ("org_id", "owner_id"):
        raw = params.get(optional)
        if raw not in (None, ""):
            body[optional] = _coerce_int(raw, field=optional)
    return "POST", "/persons", body, {}


def _build_create_activity(params: dict[str, Any]) -> RequestSpec:
    subject = _required(params, "subject")
    activity_type = _required(params, "type")
    body: dict[str, Any] = {"subject": subject, "type": activity_type}
    due_date = str(params.get("due_date") or "").strip()
    if due_date:
        body["due_date"] = due_date
    due_time = str(params.get("due_time") or "").strip()
    if due_time:
        body["due_time"] = due_time
    duration = str(params.get("duration") or "").strip()
    if duration:
        body["duration"] = duration
    note = str(params.get("note") or "").strip()
    if note:
        body["note"] = note
    for optional in ("deal_id", "person_id", "org_id", "user_id"):
        raw = params.get(optional)
        if raw not in (None, ""):
            body[optional] = _coerce_int(raw, field=optional)
    return "POST", "/activities", body, {}


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Pipedrive: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Pipedrive: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_int(raw: Any, *, field: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Pipedrive: {field!r} must be an integer"
        raise ValueError(msg) from exc


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Pipedrive: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Pipedrive: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_DEALS: _build_list_deals,
    OP_GET_DEAL: _build_get_deal,
    OP_CREATE_DEAL: _build_create_deal,
    OP_UPDATE_DEAL: _build_update_deal,
    OP_CREATE_PERSON: _build_create_person,
    OP_CREATE_ACTIVITY: _build_create_activity,
}
