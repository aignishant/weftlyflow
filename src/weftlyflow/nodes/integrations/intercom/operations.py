"""Per-operation request builders for the Intercom REST API node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Intercom's contact role is ``user`` or ``lead``; contact creation
requires at least one of ``email`` / ``external_id`` / ``phone``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.intercom.constants import (
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    OP_CREATE_CONTACT,
    OP_CREATE_CONVERSATION,
    OP_GET_CONTACT,
    OP_REPLY_CONVERSATION,
    OP_SEARCH_CONTACTS,
    OP_UPDATE_CONTACT,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_CONTACT_ROLES: frozenset[str] = frozenset({"user", "lead"})
_REPLY_TYPES: frozenset[str] = frozenset({"user", "admin"})
_REPLY_MESSAGE_TYPES: frozenset[str] = frozenset(
    {"comment", "note", "quick_reply", "close"},
)


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Intercom: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_create_contact(params: dict[str, Any]) -> RequestSpec:
    role = str(params.get("role") or "user").strip().lower() or "user"
    if role not in _CONTACT_ROLES:
        msg = f"Intercom: invalid contact role {role!r}"
        raise ValueError(msg)
    body: dict[str, Any] = {"role": role}
    email = str(params.get("email") or "").strip()
    external_id = str(params.get("external_id") or "").strip()
    phone = str(params.get("phone") or "").strip()
    if not email and not external_id and not phone:
        msg = "Intercom: one of 'email', 'external_id', or 'phone' is required"
        raise ValueError(msg)
    if email:
        body["email"] = email
    if external_id:
        body["external_id"] = external_id
    if phone:
        body["phone"] = phone
    name = str(params.get("name") or "").strip()
    if name:
        body["name"] = name
    custom_attributes = params.get("custom_attributes")
    if custom_attributes is not None:
        if not isinstance(custom_attributes, dict):
            msg = "Intercom: 'custom_attributes' must be a JSON object"
            raise ValueError(msg)
        body["custom_attributes"] = custom_attributes
    return "POST", "/contacts", body, {}


def _build_update_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "Intercom: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    path = f"/contacts/{quote(contact_id, safe='')}"
    return "PUT", path, dict(updates), {}


def _build_get_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    path = f"/contacts/{quote(contact_id, safe='')}"
    return "GET", path, None, {}


def _build_search_contacts(params: dict[str, Any]) -> RequestSpec:
    query_obj = params.get("query")
    if not isinstance(query_obj, dict) or not query_obj:
        msg = "Intercom: 'query' must be a non-empty JSON object"
        raise ValueError(msg)
    body: dict[str, Any] = {
        "query": query_obj,
        "pagination": {"per_page": _coerce_limit(params.get("per_page"))},
    }
    return "POST", "/contacts/search", body, {}


def _build_create_conversation(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    contact_type = str(params.get("contact_type") or "user").strip().lower() or "user"
    if contact_type not in _CONTACT_ROLES:
        msg = f"Intercom: invalid contact type {contact_type!r}"
        raise ValueError(msg)
    message_body = str(params.get("body") or "")
    if not message_body.strip():
        msg = "Intercom: 'body' is required for create_conversation"
        raise ValueError(msg)
    payload: dict[str, Any] = {
        "from": {"type": contact_type, "id": contact_id},
        "body": message_body,
    }
    return "POST", "/conversations", payload, {}


def _build_reply_conversation(params: dict[str, Any]) -> RequestSpec:
    conversation_id = _required(params, "conversation_id")
    reply_type = str(params.get("reply_type") or "user").strip().lower() or "user"
    if reply_type not in _REPLY_TYPES:
        msg = f"Intercom: invalid reply type {reply_type!r}"
        raise ValueError(msg)
    message_type = str(params.get("message_type") or "comment").strip().lower() or "comment"
    if message_type not in _REPLY_MESSAGE_TYPES:
        msg = f"Intercom: invalid reply message_type {message_type!r}"
        raise ValueError(msg)
    message_body = str(params.get("body") or "")
    if not message_body.strip():
        msg = "Intercom: 'body' is required for reply_conversation"
        raise ValueError(msg)
    payload: dict[str, Any] = {
        "message_type": message_type,
        "type": reply_type,
        "body": message_body,
    }
    admin_id = str(params.get("admin_id") or "").strip()
    user_id = str(params.get("user_id") or "").strip()
    if reply_type == "admin":
        if not admin_id:
            msg = "Intercom: 'admin_id' is required when reply_type='admin'"
            raise ValueError(msg)
        payload["admin_id"] = admin_id
    elif user_id:
        payload["user_id"] = user_id
    path = f"/conversations/{quote(conversation_id, safe='')}/reply"
    return "POST", path, payload, {}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Intercom: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_SEARCH_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Intercom: 'per_page' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Intercom: 'per_page' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_SEARCH_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CREATE_CONTACT: _build_create_contact,
    OP_UPDATE_CONTACT: _build_update_contact,
    OP_GET_CONTACT: _build_get_contact,
    OP_SEARCH_CONTACTS: _build_search_contacts,
    OP_CREATE_CONVERSATION: _build_create_conversation,
    OP_REPLY_CONVERSATION: _build_reply_conversation,
}
