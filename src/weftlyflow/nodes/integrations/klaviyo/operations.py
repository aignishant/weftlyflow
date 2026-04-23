"""Per-operation request builders for the Klaviyo node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://a.klaviyo.com``.

Klaviyo's v2024 JSON:API-style contract wraps every payload in a
``{"data": {"type": ..., "attributes": ...}}`` envelope — the
builders construct that shape rather than accepting free-form bodies,
so expression users never have to remember the type discriminators.

``add_profile_to_list`` uses the ``/relationships/profiles`` sub-path
and a list of ``{"type": "profile", "id": ...}`` references; that's
the JSON:API idiom for many-to-many membership mutations and is not
yet exercised by any other node.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.klaviyo.constants import (
    OP_ADD_PROFILE_TO_LIST,
    OP_CREATE_EVENT,
    OP_CREATE_PROFILE,
    OP_GET_PROFILE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Klaviyo: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_create_event(params: dict[str, Any]) -> RequestSpec:
    metric_name = _required(params, "metric_name")
    profile = params.get("profile")
    if not isinstance(profile, dict) or not profile:
        msg = "Klaviyo: 'profile' dict is required for create_event"
        raise ValueError(msg)
    properties = dict(params.get("properties") or {})
    attributes: dict[str, Any] = {
        "metric": {
            "data": {"type": "metric", "attributes": {"name": metric_name}},
        },
        "profile": {
            "data": {"type": "profile", "attributes": dict(profile)},
        },
        "properties": properties,
    }
    value = params.get("value")
    if isinstance(value, (int, float)):
        attributes["value"] = value
    body = {"data": {"type": "event", "attributes": attributes}}
    return "POST", "/api/events", body, {}


def _build_create_profile(params: dict[str, Any]) -> RequestSpec:
    attributes = params.get("attributes")
    if not isinstance(attributes, dict) or not attributes:
        msg = "Klaviyo: 'attributes' dict is required for create_profile"
        raise ValueError(msg)
    body = {"data": {"type": "profile", "attributes": dict(attributes)}}
    return "POST", "/api/profiles", body, {}


def _build_get_profile(params: dict[str, Any]) -> RequestSpec:
    profile_id = _required(params, "profile_id")
    return "GET", f"/api/profiles/{profile_id}", None, {}


def _build_add_profile_to_list(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    profile_ids = params.get("profile_ids")
    if not isinstance(profile_ids, list) or not profile_ids:
        msg = "Klaviyo: 'profile_ids' must be a non-empty list"
        raise ValueError(msg)
    references = [
        {"type": "profile", "id": str(pid)} for pid in profile_ids
    ]
    body = {"data": references}
    return "POST", f"/api/lists/{list_id}/relationships/profiles", body, {}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Klaviyo: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CREATE_EVENT: _build_create_event,
    OP_CREATE_PROFILE: _build_create_profile,
    OP_GET_PROFILE: _build_get_profile,
    OP_ADD_PROFILE_TO_LIST: _build_add_profile_to_list,
}
