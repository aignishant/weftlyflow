"""Per-operation request builders for the HubSpot CRM v3 contacts node.

Each builder returns ``(http_method, path, json_body, query_params)``.
All contact operations hit ``/crm/v3/objects/contacts``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.hubspot.constants import (
    API_VERSION_PREFIX,
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    OP_CREATE_CONTACT,
    OP_DELETE_CONTACT,
    OP_GET_CONTACT,
    OP_SEARCH_CONTACTS,
    OP_UPDATE_CONTACT,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_CONTACTS_PATH: str = f"{API_VERSION_PREFIX}/objects/contacts"
_SEARCH_PATH: str = f"{API_VERSION_PREFIX}/objects/contacts/search"


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"HubSpot: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_create_contact(params: dict[str, Any]) -> RequestSpec:
    properties = _required_properties(params)
    return "POST", _CONTACTS_PATH, {"properties": properties}, {}


def _build_update_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    properties = _required_properties(params)
    path = f"{_CONTACTS_PATH}/{quote(contact_id, safe='')}"
    return "PATCH", path, {"properties": properties}, {}


def _build_get_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    path = f"{_CONTACTS_PATH}/{quote(contact_id, safe='')}"
    query: dict[str, Any] = {}
    fields = _coerce_string_list(params.get("properties"))
    if fields:
        query["properties"] = ",".join(fields)
    return "GET", path, None, query


def _build_delete_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    path = f"{_CONTACTS_PATH}/{quote(contact_id, safe='')}"
    return "DELETE", path, None, {}


def _build_search_contacts(params: dict[str, Any]) -> RequestSpec:
    body: dict[str, Any] = {}
    query_text = str(params.get("query") or "").strip()
    if query_text:
        body["query"] = query_text
    filter_groups = params.get("filter_groups")
    if filter_groups is not None:
        if not isinstance(filter_groups, list):
            msg = "HubSpot: 'filter_groups' must be a list"
            raise ValueError(msg)
        body["filterGroups"] = filter_groups
    sorts = params.get("sorts")
    if sorts is not None:
        if not isinstance(sorts, list):
            msg = "HubSpot: 'sorts' must be a list"
            raise ValueError(msg)
        body["sorts"] = sorts
    fields = _coerce_string_list(params.get("properties"))
    if fields:
        body["properties"] = fields
    limit = params.get("limit")
    body["limit"] = _coerce_limit(limit)
    after = str(params.get("after") or "").strip()
    if after:
        body["after"] = after
    return "POST", _SEARCH_PATH, body, {}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"HubSpot: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_properties(params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("properties")
    if not isinstance(raw, dict) or not raw:
        msg = "HubSpot: 'properties' must be a non-empty JSON object"
        raise ValueError(msg)
    return raw


def _coerce_string_list(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = "HubSpot: 'properties' must be a string or list of strings"
    raise ValueError(msg)


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_SEARCH_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "HubSpot: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "HubSpot: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_SEARCH_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CREATE_CONTACT: _build_create_contact,
    OP_UPDATE_CONTACT: _build_update_contact,
    OP_GET_CONTACT: _build_get_contact,
    OP_DELETE_CONTACT: _build_delete_contact,
    OP_SEARCH_CONTACTS: _build_search_contacts,
}
