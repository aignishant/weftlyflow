"""Per-operation request builders for the GA4 Measurement Protocol node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to :data:`API_BASE_URL`. Auth (``measurement_id`` /
``api_secret``) is appended to the query by the credential's
:meth:`inject`, not here.

GA4's request envelope is always the same dict:

``{"client_id": "...", "user_id": "...", "events": [{"name": ..., "params": ...}], ...}``

Operations differ only in which target path they hit and whether they
carry a single-event or batch-event payload; ``user_properties`` is a
convenience that sends a no-op ``session_start`` event with
``user_properties`` attached.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.ga4.constants import (
    COLLECT_PATH,
    DEBUG_COLLECT_PATH,
    OP_TRACK_EVENT,
    OP_TRACK_EVENTS,
    OP_USER_PROPERTIES,
    OP_VALIDATE_EVENT,
)

RequestSpec = tuple[str, str, dict[str, Any], dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"GA4: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_track_event(params: dict[str, Any]) -> RequestSpec:
    body = _base_envelope(params)
    body["events"] = [_single_event(params)]
    return "POST", COLLECT_PATH, body, {}


def _build_track_events(params: dict[str, Any]) -> RequestSpec:
    events = params.get("events")
    if not isinstance(events, list) or not events:
        msg = "GA4: 'events' must be a non-empty list for track_events"
        raise ValueError(msg)
    body = _base_envelope(params)
    body["events"] = [_coerce_event(e) for e in events]
    return "POST", COLLECT_PATH, body, {}


def _build_validate_event(params: dict[str, Any]) -> RequestSpec:
    body = _base_envelope(params)
    body["events"] = [_single_event(params)]
    return "POST", DEBUG_COLLECT_PATH, body, {}


def _build_user_properties(params: dict[str, Any]) -> RequestSpec:
    user_properties = params.get("user_properties")
    if not isinstance(user_properties, dict) or not user_properties:
        msg = "GA4: 'user_properties' dict is required for user_properties"
        raise ValueError(msg)
    body = _base_envelope(params)
    body["user_properties"] = {
        str(k): {"value": v} for k, v in user_properties.items()
    }
    body["events"] = [{"name": "session_start", "params": {}}]
    return "POST", COLLECT_PATH, body, {}


def _base_envelope(params: dict[str, Any]) -> dict[str, Any]:
    client_id = _required_str(params, "client_id")
    out: dict[str, Any] = {"client_id": client_id}
    user_id = str(params.get("user_id") or "").strip()
    if user_id:
        out["user_id"] = user_id
    timestamp = params.get("timestamp_micros")
    if isinstance(timestamp, int) and timestamp > 0:
        out["timestamp_micros"] = timestamp
    non_personalized = params.get("non_personalized_ads")
    if isinstance(non_personalized, bool):
        out["non_personalized_ads"] = non_personalized
    return out


def _single_event(params: dict[str, Any]) -> dict[str, Any]:
    name = _required_str(params, "event_name")
    event: dict[str, Any] = {"name": name}
    event_params = params.get("event_params")
    if isinstance(event_params, dict):
        event["params"] = dict(event_params)
    else:
        event["params"] = {}
    return event


def _coerce_event(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        msg = "GA4: each entry in 'events' must be a dict"
        raise ValueError(msg)
    name = str(raw.get("name") or "").strip()
    if not name:
        msg = "GA4: each event needs a non-empty 'name'"
        raise ValueError(msg)
    event_params = raw.get("params")
    return {
        "name": name,
        "params": dict(event_params) if isinstance(event_params, dict) else {},
    }


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"GA4: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_TRACK_EVENT: _build_track_event,
    OP_TRACK_EVENTS: _build_track_events,
    OP_VALIDATE_EVENT: _build_validate_event,
    OP_USER_PROPERTIES: _build_user_properties,
}
