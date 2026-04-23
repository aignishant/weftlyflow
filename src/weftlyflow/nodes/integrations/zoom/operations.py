"""Per-operation request builders for the Zoom Meetings node.

Each builder returns ``(http_method, path, body, query)``. Paths are
prefixed with :data:`API_BASE_URL` by the node layer.

Zoom's list endpoints are keyed by user (``/users/{userId}/meetings``)
rather than a cluster-wide listing — the builder accepts a ``user_id``
of ``"me"`` as a shorthand to target the token's owning user.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.zoom.constants import (
    DEFAULT_PAGE_SIZE,
    LIST_TYPES,
    MAX_PAGE_SIZE,
    OP_CREATE_MEETING,
    OP_DELETE_MEETING,
    OP_GET_MEETING,
    OP_LIST_MEETINGS,
    OP_LIST_PAST_PARTICIPANTS,
    OP_UPDATE_MEETING,
    VALID_MEETING_TYPES,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Zoom: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_meetings(params: dict[str, Any]) -> RequestSpec:
    user_id = str(params.get("user_id") or "me").strip() or "me"
    query: dict[str, Any] = {"page_size": _coerce_page_size(params.get("page_size"))}
    list_type = str(params.get("list_type") or "").strip()
    if list_type:
        if list_type not in LIST_TYPES:
            msg = f"Zoom: 'list_type' must be one of {sorted(LIST_TYPES)!r}"
            raise ValueError(msg)
        query["type"] = list_type
    cursor = str(params.get("next_page_token") or "").strip()
    if cursor:
        query["next_page_token"] = cursor
    path = f"/users/{quote(user_id, safe='')}/meetings"
    return "GET", path, None, query


def _build_get_meeting(params: dict[str, Any]) -> RequestSpec:
    meeting_id = _required_id(params)
    return "GET", f"/meetings/{meeting_id}", None, {}


def _build_create_meeting(params: dict[str, Any]) -> RequestSpec:
    user_id = str(params.get("user_id") or "me").strip() or "me"
    topic = _required(params, "topic")
    body: dict[str, Any] = {"topic": topic}
    meeting_type = params.get("type")
    if meeting_type is not None:
        body["type"] = _coerce_meeting_type(meeting_type)
    for optional in ("start_time", "duration", "timezone", "agenda", "password"):
        value = params.get(optional)
        if value not in (None, ""):
            body[optional] = value
    settings = params.get("settings")
    if isinstance(settings, dict) and settings:
        body["settings"] = dict(settings)
    path = f"/users/{quote(user_id, safe='')}/meetings"
    return "POST", path, body, {}


def _build_update_meeting(params: dict[str, Any]) -> RequestSpec:
    meeting_id = _required_id(params)
    patch = params.get("document")
    if not isinstance(patch, dict) or not patch:
        msg = "Zoom: 'document' must be a non-empty JSON object"
        raise ValueError(msg)
    return "PATCH", f"/meetings/{meeting_id}", dict(patch), {}


def _build_delete_meeting(params: dict[str, Any]) -> RequestSpec:
    meeting_id = _required_id(params)
    query: dict[str, Any] = {}
    occurrence_id = str(params.get("occurrence_id") or "").strip()
    if occurrence_id:
        query["occurrence_id"] = occurrence_id
    return "DELETE", f"/meetings/{meeting_id}", None, query


def _build_list_past_participants(params: dict[str, Any]) -> RequestSpec:
    meeting_id = _required_id(params)
    query: dict[str, Any] = {"page_size": _coerce_page_size(params.get("page_size"))}
    cursor = str(params.get("next_page_token") or "").strip()
    if cursor:
        query["next_page_token"] = cursor
    path = f"/past_meetings/{meeting_id}/participants"
    return "GET", path, None, query


def _coerce_page_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Zoom: 'page_size' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Zoom: 'page_size' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_SIZE)


def _coerce_meeting_type(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Zoom: 'type' must be an integer"
        raise ValueError(msg) from exc
    if value not in VALID_MEETING_TYPES:
        msg = f"Zoom: 'type' must be one of {sorted(VALID_MEETING_TYPES)!r}"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Zoom: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_id(params: dict[str, Any]) -> str:
    raw = params.get("meeting_id")
    if raw in (None, ""):
        msg = "Zoom: 'meeting_id' is required"
        raise ValueError(msg)
    return quote(str(raw).strip(), safe="")


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_MEETINGS: _build_list_meetings,
    OP_GET_MEETING: _build_get_meeting,
    OP_CREATE_MEETING: _build_create_meeting,
    OP_UPDATE_MEETING: _build_update_meeting,
    OP_DELETE_MEETING: _build_delete_meeting,
    OP_LIST_PAST_PARTICIPANTS: _build_list_past_participants,
}
