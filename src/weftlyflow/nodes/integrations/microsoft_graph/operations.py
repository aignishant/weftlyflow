"""Per-operation request builders for the Microsoft Graph node.

Each builder returns ``(http_method, path, body, query, advanced)``.

The fifth tuple element — ``advanced`` — is Graph-specific. It flags
operations that require *advanced-query* semantics: ``$count``,
``$search``, and certain ``$filter`` expressions on directory
resources. When set, the node layer emits the distinctive
``ConsistencyLevel: eventual`` header that Graph uses to authorize the
eventually-consistent directory index. Only *some* list operations
need it, determined at build time from the query parameters.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.microsoft_graph.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    OP_CREATE_EVENT,
    OP_GET_USER,
    OP_LIST_EVENTS,
    OP_LIST_MESSAGES,
    OP_LIST_USERS,
    OP_SEND_MAIL,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any], bool]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Microsoft Graph: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_users(params: dict[str, Any]) -> RequestSpec:
    query, advanced = _build_list_query(params)
    return "GET", "/users", None, query, advanced


def _build_get_user(params: dict[str, Any]) -> RequestSpec:
    user_id = _required(params, "user_id")
    query: dict[str, Any] = {}
    select = _coerce_string_list(params.get("select"), field="select")
    if select:
        query["$select"] = ",".join(select)
    return "GET", f"/users/{quote(user_id, safe='')}", None, query, False


def _build_list_messages(params: dict[str, Any]) -> RequestSpec:
    user_id = str(params.get("user_id") or "me").strip() or "me"
    query, advanced = _build_list_query(params)
    path = "/me/messages" if user_id == "me" else f"/users/{quote(user_id, safe='')}/messages"
    return "GET", path, None, query, advanced


def _build_send_mail(params: dict[str, Any]) -> RequestSpec:
    user_id = str(params.get("user_id") or "me").strip() or "me"
    message = params.get("message")
    if not isinstance(message, dict) or not message:
        msg = "Microsoft Graph: 'message' must be a non-empty JSON object"
        raise ValueError(msg)
    body: dict[str, Any] = {"message": dict(message)}
    save = params.get("save_to_sent_items")
    if save is not None:
        body["saveToSentItems"] = _coerce_bool(save)
    path = "/me/sendMail" if user_id == "me" else f"/users/{quote(user_id, safe='')}/sendMail"
    return "POST", path, body, {}, False


def _build_list_events(params: dict[str, Any]) -> RequestSpec:
    user_id = str(params.get("user_id") or "me").strip() or "me"
    query, advanced = _build_list_query(params)
    path = "/me/events" if user_id == "me" else f"/users/{quote(user_id, safe='')}/events"
    return "GET", path, None, query, advanced


def _build_create_event(params: dict[str, Any]) -> RequestSpec:
    user_id = str(params.get("user_id") or "me").strip() or "me"
    event = params.get("event")
    if not isinstance(event, dict) or not event:
        msg = "Microsoft Graph: 'event' must be a non-empty JSON object"
        raise ValueError(msg)
    path = "/me/events" if user_id == "me" else f"/users/{quote(user_id, safe='')}/events"
    return "POST", path, dict(event), {}, False


def _build_list_query(params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    query: dict[str, Any] = {"$top": _coerce_page_size(params.get("top"))}
    select = _coerce_string_list(params.get("select"), field="select")
    if select:
        query["$select"] = ",".join(select)
    order_by = str(params.get("order_by") or "").strip()
    if order_by:
        query["$orderby"] = order_by
    filter_expr = str(params.get("filter") or "").strip()
    if filter_expr:
        query["$filter"] = filter_expr
    search = str(params.get("search") or "").strip()
    if search:
        query["$search"] = search
    count = params.get("count")
    want_count = count is not None and _coerce_bool(count) == "true"
    if want_count:
        query["$count"] = "true"
    skip_token = str(params.get("skip_token") or "").strip()
    if skip_token:
        query["$skiptoken"] = skip_token
    advanced = bool(search or want_count or (filter_expr and _filter_needs_advanced(filter_expr)))
    return query, advanced


def _filter_needs_advanced(expr: str) -> bool:
    lowered = expr.lower()
    return any(token in lowered for token in ("endswith(", "ne ", "not(", "startswith("))


def _coerce_page_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Microsoft Graph: 'top' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Microsoft Graph: 'top' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_SIZE)


def _coerce_bool(raw: Any) -> str:
    if isinstance(raw, bool):
        return "true" if raw else "false"
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes"}:
        return "true"
    if text in {"false", "0", "no"}:
        return "false"
    msg = f"Microsoft Graph: boolean flag must be true/false, got {raw!r}"
    raise ValueError(msg)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Microsoft Graph: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Microsoft Graph: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_USERS: _build_list_users,
    OP_GET_USER: _build_get_user,
    OP_LIST_MESSAGES: _build_list_messages,
    OP_SEND_MAIL: _build_send_mail,
    OP_LIST_EVENTS: _build_list_events,
    OP_CREATE_EVENT: _build_create_event,
}
