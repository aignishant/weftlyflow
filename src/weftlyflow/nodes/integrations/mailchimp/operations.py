"""Per-operation request builders for the Mailchimp Marketing v3 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Mailchimp identifies list members by the MD5 hash of the lowercased
email address — the builder computes that hash so callers can pass the
plain email.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.mailchimp.constants import (
    API_VERSION_PREFIX,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    MEMBER_STATUSES,
    OP_ADD_MEMBER,
    OP_GET_LIST,
    OP_GET_MEMBER,
    OP_LIST_LISTS,
    OP_TAG_MEMBER,
    OP_UPDATE_MEMBER,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Mailchimp: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def subscriber_hash(email: str) -> str:
    """Return the MD5 hash Mailchimp uses to identify list members.

    Mailchimp's API mandates MD5 for subscriber hashes; this is not a
    security primitive.
    """
    return hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()


def _build_list_lists(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"count": _coerce_limit(params.get("count"))}
    offset = params.get("offset")
    if offset is not None and offset != "":
        try:
            offset_value = int(offset)
        except (TypeError, ValueError) as exc:
            msg = "Mailchimp: 'offset' must be an integer"
            raise ValueError(msg) from exc
        if offset_value < 0:
            msg = "Mailchimp: 'offset' must be >= 0"
            raise ValueError(msg)
        query["offset"] = offset_value
    return "GET", f"{API_VERSION_PREFIX}/lists", None, query


def _build_get_list(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    path = f"{API_VERSION_PREFIX}/lists/{quote(list_id, safe='')}"
    return "GET", path, None, {}


def _build_add_member(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    email = _required(params, "email")
    status = str(params.get("status") or "subscribed").strip().lower() or "subscribed"
    if status not in MEMBER_STATUSES:
        msg = f"Mailchimp: invalid status {status!r}"
        raise ValueError(msg)
    body: dict[str, Any] = {"email_address": email, "status": status}
    merge_fields = params.get("merge_fields")
    if merge_fields is not None:
        if not isinstance(merge_fields, dict):
            msg = "Mailchimp: 'merge_fields' must be a JSON object"
            raise ValueError(msg)
        body["merge_fields"] = merge_fields
    tags = _coerce_string_list(params.get("tags"), field="tags")
    if tags:
        body["tags"] = tags
    path = f"{API_VERSION_PREFIX}/lists/{quote(list_id, safe='')}/members"
    return "POST", path, body, {}


def _build_update_member(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    email = _required(params, "email")
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "Mailchimp: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    status = updates.get("status")
    if isinstance(status, str) and status.lower() not in MEMBER_STATUSES:
        msg = f"Mailchimp: invalid status {status!r}"
        raise ValueError(msg)
    path = (
        f"{API_VERSION_PREFIX}/lists/{quote(list_id, safe='')}"
        f"/members/{subscriber_hash(email)}"
    )
    return "PATCH", path, dict(updates), {}


def _build_get_member(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    email = _required(params, "email")
    path = (
        f"{API_VERSION_PREFIX}/lists/{quote(list_id, safe='')}"
        f"/members/{subscriber_hash(email)}"
    )
    return "GET", path, None, {}


def _build_tag_member(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    email = _required(params, "email")
    add_tags = _coerce_string_list(params.get("add_tags"), field="add_tags")
    remove_tags = _coerce_string_list(params.get("remove_tags"), field="remove_tags")
    if not add_tags and not remove_tags:
        msg = "Mailchimp: tag_member requires 'add_tags' or 'remove_tags'"
        raise ValueError(msg)
    tags_payload: list[dict[str, str]] = [
        {"name": tag, "status": "active"} for tag in add_tags
    ]
    tags_payload.extend({"name": tag, "status": "inactive"} for tag in remove_tags)
    path = (
        f"{API_VERSION_PREFIX}/lists/{quote(list_id, safe='')}"
        f"/members/{subscriber_hash(email)}/tags"
    )
    return "POST", path, {"tags": tags_payload}, {}


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Mailchimp: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Mailchimp: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Mailchimp: 'count' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Mailchimp: 'count' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_LISTS: _build_list_lists,
    OP_GET_LIST: _build_get_list,
    OP_ADD_MEMBER: _build_add_member,
    OP_UPDATE_MEMBER: _build_update_member,
    OP_GET_MEMBER: _build_get_member,
    OP_TAG_MEMBER: _build_tag_member,
}
