"""Per-operation request builders for the Freshdesk v2 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Freshdesk exposes tickets and contacts at ``/api/v2/*``; the node layer
prepends the per-tenant ``https://<sub>.freshdesk.com/api/v2`` prefix.
Priority/status/source enums are folded into their integer codes here
so callers can use human-readable labels.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.freshdesk.constants import (
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    OP_CREATE_CONTACT,
    OP_CREATE_TICKET,
    OP_GET_TICKET,
    OP_LIST_CONTACTS,
    OP_LIST_TICKETS,
    OP_UPDATE_TICKET,
    TICKET_PRIORITIES,
    TICKET_SOURCES,
    TICKET_STATUSES,
    TICKET_UPDATE_FIELDS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Freshdesk: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_tickets(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"per_page": _coerce_per_page(params.get("per_page"))}
    page = _coerce_page(params.get("page"))
    if page is not None:
        query["page"] = page
    updated_since = str(params.get("updated_since") or "").strip()
    if updated_since:
        query["updated_since"] = updated_since
    return "GET", "/tickets", None, query


def _build_get_ticket(params: dict[str, Any]) -> RequestSpec:
    ticket_id = _required(params, "ticket_id")
    return "GET", f"/tickets/{quote(ticket_id, safe='')}", None, {}


def _build_create_ticket(params: dict[str, Any]) -> RequestSpec:
    subject = _required(params, "subject")
    description = _required(params, "description")
    email = _required(params, "email")
    body: dict[str, Any] = {
        "subject": subject,
        "description": description,
        "email": email,
        "priority": _coerce_priority(params.get("priority", "medium")),
        "status": _coerce_status(params.get("status", "open")),
    }
    source = params.get("source")
    if source not in (None, ""):
        body["source"] = _coerce_source(source)
    ticket_type = str(params.get("type") or "").strip()
    if ticket_type:
        body["type"] = ticket_type
    tags = _coerce_string_list(params.get("tags"), field="tags")
    if tags:
        body["tags"] = tags
    return "POST", "/tickets", body, {}


def _build_update_ticket(params: dict[str, Any]) -> RequestSpec:
    ticket_id = _required(params, "ticket_id")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Freshdesk: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    unknown = [k for k in fields if k not in TICKET_UPDATE_FIELDS]
    if unknown:
        msg = f"Freshdesk: unknown ticket field(s) {unknown!r}"
        raise ValueError(msg)
    body = dict(fields)
    if "priority" in body and isinstance(body["priority"], str):
        body["priority"] = _coerce_priority(body["priority"])
    if "status" in body and isinstance(body["status"], str):
        body["status"] = _coerce_status(body["status"])
    if "source" in body and isinstance(body["source"], str):
        body["source"] = _coerce_source(body["source"])
    return "PUT", f"/tickets/{quote(ticket_id, safe='')}", body, {}


def _build_list_contacts(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"per_page": _coerce_per_page(params.get("per_page"))}
    page = _coerce_page(params.get("page"))
    if page is not None:
        query["page"] = page
    email = str(params.get("email") or "").strip()
    if email:
        query["email"] = email
    return "GET", "/contacts", None, query


def _build_create_contact(params: dict[str, Any]) -> RequestSpec:
    name = _required(params, "name")
    body: dict[str, Any] = {"name": name}
    email = str(params.get("email") or "").strip()
    phone = str(params.get("phone") or "").strip()
    mobile = str(params.get("mobile") or "").strip()
    if not any([email, phone, mobile]):
        msg = "Freshdesk: contact requires one of 'email', 'phone', or 'mobile'"
        raise ValueError(msg)
    if email:
        body["email"] = email
    if phone:
        body["phone"] = phone
    if mobile:
        body["mobile"] = mobile
    company_id = _coerce_optional_int(params.get("company_id"), field="company_id")
    if company_id is not None:
        body["company_id"] = company_id
    return "POST", "/contacts", body, {}


def _coerce_priority(raw: Any) -> int:
    if isinstance(raw, int) and raw in TICKET_PRIORITIES.values():
        return raw
    key = str(raw or "").strip().lower()
    if key not in TICKET_PRIORITIES:
        msg = f"Freshdesk: invalid priority {raw!r}"
        raise ValueError(msg)
    return TICKET_PRIORITIES[key]


def _coerce_status(raw: Any) -> int:
    if isinstance(raw, int) and raw in TICKET_STATUSES.values():
        return raw
    key = str(raw or "").strip().lower()
    if key not in TICKET_STATUSES:
        msg = f"Freshdesk: invalid status {raw!r}"
        raise ValueError(msg)
    return TICKET_STATUSES[key]


def _coerce_source(raw: Any) -> int:
    if isinstance(raw, int) and raw in TICKET_SOURCES.values():
        return raw
    key = str(raw or "").strip().lower()
    if key not in TICKET_SOURCES:
        msg = f"Freshdesk: invalid source {raw!r}"
        raise ValueError(msg)
    return TICKET_SOURCES[key]


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Freshdesk: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _coerce_per_page(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PER_PAGE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Freshdesk: 'per_page' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Freshdesk: 'per_page' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PER_PAGE)


def _coerce_optional_int(raw: Any, *, field: str) -> int | None:
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Freshdesk: {field!r} must be an integer"
        raise ValueError(msg) from exc


def _coerce_page(raw: Any) -> int | None:
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Freshdesk: 'page' must be an integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Freshdesk: 'page' must be >= 1"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Freshdesk: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_TICKETS: _build_list_tickets,
    OP_GET_TICKET: _build_get_ticket,
    OP_CREATE_TICKET: _build_create_ticket,
    OP_UPDATE_TICKET: _build_update_ticket,
    OP_LIST_CONTACTS: _build_list_contacts,
    OP_CREATE_CONTACT: _build_create_contact,
}
