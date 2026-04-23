"""Per-operation request builders for the ActiveCampaign node.

Each builder returns ``(http_method, path, body, query)``. Paths are
prefixed with the ``/api/3`` root already baked into the tenant base
URL.

Body-wrapping quirks:

* ``create_contact`` / ``update_contact`` wrap the payload in
  ``{"contact": {...}}``.
* ``add_contact_to_list`` posts
  ``{"contactList": {"list": ..., "contact": ..., "status": 1}}``.
* ``add_tag_to_contact`` posts
  ``{"contactTag": {"contact": ..., "tag": ...}}``.

These envelope names are not Bearer-style shared conventions — each
resource has its own declarative wrapper.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.activecampaign.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    OP_ADD_CONTACT_TO_LIST,
    OP_ADD_TAG_TO_CONTACT,
    OP_CREATE_CONTACT,
    OP_DELETE_CONTACT,
    OP_GET_CONTACT,
    OP_LIST_CONTACTS,
    OP_LIST_TAGS,
    OP_UPDATE_CONTACT,
    VALID_LIST_STATUSES,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"ActiveCampaign: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_contacts(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_page_size(params.get("limit"))}
    offset = params.get("offset")
    if offset is not None and offset != "":
        query["offset"] = _coerce_non_negative_int(offset, field="offset")
    email = str(params.get("email") or "").strip()
    if email:
        query["email"] = email
    search = str(params.get("search") or "").strip()
    if search:
        query["search"] = search
    list_id = str(params.get("list_id") or "").strip()
    if list_id:
        query["listid"] = list_id
    return "GET", "/contacts", None, query


def _build_get_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    return "GET", f"/contacts/{quote(contact_id, safe='')}", None, {}


def _build_create_contact(params: dict[str, Any]) -> RequestSpec:
    document = _coerce_document(params.get("document"))
    email = str(document.get("email") or "").strip()
    if not email:
        msg = "ActiveCampaign: 'document.email' is required"
        raise ValueError(msg)
    body: dict[str, Any] = {"contact": document}
    return "POST", "/contacts", body, {}


def _build_update_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    document = _coerce_document(params.get("document"))
    body: dict[str, Any] = {"contact": document}
    return "PUT", f"/contacts/{quote(contact_id, safe='')}", body, {}


def _build_delete_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    return "DELETE", f"/contacts/{quote(contact_id, safe='')}", None, {}


def _build_add_contact_to_list(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    list_id = _required(params, "list_id")
    status_raw = params.get("status")
    status = 1 if status_raw in (None, "") else _coerce_list_status(status_raw)
    body: dict[str, Any] = {
        "contactList": {
            "list": list_id,
            "contact": contact_id,
            "status": status,
        },
    }
    return "POST", "/contactLists", body, {}


def _build_add_tag_to_contact(params: dict[str, Any]) -> RequestSpec:
    contact_id = _required(params, "contact_id")
    tag_id = _required(params, "tag_id")
    body: dict[str, Any] = {
        "contactTag": {"contact": contact_id, "tag": tag_id},
    }
    return "POST", "/contactTags", body, {}


def _build_list_tags(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_page_size(params.get("limit"))}
    offset = params.get("offset")
    if offset is not None and offset != "":
        query["offset"] = _coerce_non_negative_int(offset, field="offset")
    search = str(params.get("search") or "").strip()
    if search:
        query["search"] = search
    return "GET", "/tags", None, query


def _coerce_document(raw: Any) -> dict[str, Any]:
    if raw is None:
        msg = "ActiveCampaign: 'document' is required"
        raise ValueError(msg)
    if not isinstance(raw, dict):
        msg = "ActiveCampaign: 'document' must be a JSON object"
        raise ValueError(msg)
    if not raw:
        msg = "ActiveCampaign: 'document' must be a non-empty object"
        raise ValueError(msg)
    return dict(raw)


def _coerce_list_status(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "ActiveCampaign: 'status' must be 1 (subscribe) or 2 (unsubscribe)"
        raise ValueError(msg) from exc
    if value not in VALID_LIST_STATUSES:
        msg = "ActiveCampaign: 'status' must be 1 (subscribe) or 2 (unsubscribe)"
        raise ValueError(msg)
    return value


def _coerce_non_negative_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"ActiveCampaign: {field!r} must be a non-negative integer"
        raise ValueError(msg) from exc
    return max(0, value)


def _coerce_page_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "ActiveCampaign: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "ActiveCampaign: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_SIZE)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"ActiveCampaign: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_CONTACTS: _build_list_contacts,
    OP_GET_CONTACT: _build_get_contact,
    OP_CREATE_CONTACT: _build_create_contact,
    OP_UPDATE_CONTACT: _build_update_contact,
    OP_DELETE_CONTACT: _build_delete_contact,
    OP_ADD_CONTACT_TO_LIST: _build_add_contact_to_list,
    OP_ADD_TAG_TO_CONTACT: _build_add_tag_to_contact,
    OP_LIST_TAGS: _build_list_tags,
}
