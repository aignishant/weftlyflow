"""Per-operation request builders for the Zendesk Support v2 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Zendesk wraps most request/response bodies in a single root key
(``ticket``, ``tickets``, ``comment``); the node layer handles that
envelope here so the user-facing parameters stay flat.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.zendesk.constants import (
    API_VERSION_PREFIX,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    OP_ADD_COMMENT,
    OP_CREATE_TICKET,
    OP_GET_TICKET,
    OP_LIST_TICKETS,
    OP_SEARCH,
    OP_UPDATE_TICKET,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_CREATE_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "subject",
        "priority",
        "status",
        "type",
        "tags",
        "requester_id",
        "assignee_id",
        "group_id",
        "external_id",
        "custom_fields",
    },
)
_UPDATE_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "subject",
        "priority",
        "status",
        "type",
        "tags",
        "additional_tags",
        "remove_tags",
        "assignee_id",
        "group_id",
        "external_id",
        "custom_fields",
    },
)
_TICKET_PRIORITIES: frozenset[str] = frozenset(
    {"urgent", "high", "normal", "low"},
)
_TICKET_STATUSES: frozenset[str] = frozenset(
    {"new", "open", "pending", "hold", "solved", "closed"},
)


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Zendesk: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_ticket(params: dict[str, Any]) -> RequestSpec:
    ticket_id = _required_id(params, "ticket_id")
    path = f"{API_VERSION_PREFIX}/tickets/{ticket_id}.json"
    return "GET", path, None, {}


def _build_create_ticket(params: dict[str, Any]) -> RequestSpec:
    subject = _required(params, "subject")
    comment_body = _required(params, "comment")
    ticket: dict[str, Any] = {
        "subject": subject,
        "comment": {"body": comment_body},
    }
    priority = str(params.get("priority") or "").strip().lower()
    if priority:
        if priority not in _TICKET_PRIORITIES:
            msg = f"Zendesk: invalid priority {priority!r}"
            raise ValueError(msg)
        ticket["priority"] = priority
    extra = params.get("extra_fields")
    if extra is not None:
        if not isinstance(extra, dict):
            msg = "Zendesk: 'extra_fields' must be a JSON object"
            raise ValueError(msg)
        for key, value in extra.items():
            if key not in _CREATE_ALLOWED_FIELDS:
                msg = f"Zendesk: unknown create ticket field {key!r}"
                raise ValueError(msg)
            ticket[key] = value
    return "POST", f"{API_VERSION_PREFIX}/tickets.json", {"ticket": ticket}, {}


def _build_update_ticket(params: dict[str, Any]) -> RequestSpec:
    ticket_id = _required_id(params, "ticket_id")
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "Zendesk: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    for key in updates:
        if key not in _UPDATE_ALLOWED_FIELDS:
            msg = f"Zendesk: unknown ticket field {key!r}"
            raise ValueError(msg)
    status = updates.get("status")
    if isinstance(status, str) and status.lower() not in _TICKET_STATUSES:
        msg = f"Zendesk: invalid status {status!r}"
        raise ValueError(msg)
    path = f"{API_VERSION_PREFIX}/tickets/{ticket_id}.json"
    return "PUT", path, {"ticket": dict(updates)}, {}


def _build_list_tickets(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"per_page": _coerce_limit(params.get("per_page"))}
    page = params.get("page")
    if page is not None and page != "":
        try:
            page_value = int(page)
        except (TypeError, ValueError) as exc:
            msg = "Zendesk: 'page' must be an integer"
            raise ValueError(msg) from exc
        if page_value < 1:
            msg = "Zendesk: 'page' must be >= 1"
            raise ValueError(msg)
        query["page"] = page_value
    return "GET", f"{API_VERSION_PREFIX}/tickets.json", None, query


def _build_add_comment(params: dict[str, Any]) -> RequestSpec:
    ticket_id = _required_id(params, "ticket_id")
    comment_body = _required(params, "comment")
    public = bool(params.get("public", True))
    ticket_patch: dict[str, Any] = {
        "comment": {"body": comment_body, "public": public},
    }
    path = f"{API_VERSION_PREFIX}/tickets/{ticket_id}.json"
    return "PUT", path, {"ticket": ticket_patch}, {}


def _build_search(params: dict[str, Any]) -> RequestSpec:
    query = str(params.get("query") or "").strip()
    if not query:
        msg = "Zendesk: 'query' is required for search"
        raise ValueError(msg)
    params_out: dict[str, Any] = {
        "query": query,
        "per_page": _coerce_limit(params.get("per_page")),
    }
    sort_by = str(params.get("sort_by") or "").strip()
    if sort_by:
        params_out["sort_by"] = sort_by
    sort_order = str(params.get("sort_order") or "").strip().lower()
    if sort_order:
        if sort_order not in {"asc", "desc"}:
            msg = f"Zendesk: invalid sort_order {sort_order!r}"
            raise ValueError(msg)
        params_out["sort_order"] = sort_order
    return "GET", f"{API_VERSION_PREFIX}/search.json", None, params_out


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Zendesk: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_id(params: dict[str, Any], key: str) -> str:
    raw = params.get(key)
    if raw is None or raw == "":
        msg = f"Zendesk: {key!r} is required"
        raise ValueError(msg)
    try:
        numeric = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Zendesk: {key!r} must be an integer"
        raise ValueError(msg) from exc
    if numeric < 1:
        msg = f"Zendesk: {key!r} must be >= 1"
        raise ValueError(msg)
    return str(numeric)


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Zendesk: 'per_page' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Zendesk: 'per_page' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_TICKET: _build_get_ticket,
    OP_CREATE_TICKET: _build_create_ticket,
    OP_UPDATE_TICKET: _build_update_ticket,
    OP_LIST_TICKETS: _build_list_tickets,
    OP_ADD_COMMENT: _build_add_comment,
    OP_SEARCH: _build_search,
}
