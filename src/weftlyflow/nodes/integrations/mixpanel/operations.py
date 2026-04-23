"""Per-operation request builders for the Mixpanel node.

Each builder returns ``(http_method, path, body, query)`` where
``body`` may be ``None`` (ingestion that rides in the query string) or
a list/dict (for ``/import``'s JSON array body).

Distinctive Mixpanel shape:

* **Ingestion** (``/track``, ``/engage``, ``/groups``) takes the event
  payload, serializes it to JSON, base64-encodes it, and sends the
  base64 string as the ``?data=`` **query parameter** on an
  otherwise-bodyless POST. No other node in the catalog ships
  base64-in-query as its primary body channel.
* **``/import``** is the only path that accepts a regular JSON array
  body, which is why the node applies Basic auth with ``api_secret``
  there rather than using the no-op credential-in-body idiom.

The builders assemble the **decoded** event dicts. The node is
responsible for base64-encoding and sliding the result into the query
string for ingestion operations, and for wiring the ``api_secret``
through an ephemeral basic-auth injector for ``import_events``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.mixpanel.constants import (
    OP_ENGAGE_USER,
    OP_IMPORT_EVENTS,
    OP_TRACK_EVENT,
    OP_UPDATE_GROUP,
)

RequestSpec = tuple[str, str, Any, dict[str, Any]]


def build_request(
    operation: str, params: dict[str, Any], *, project_token: str,
) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Mixpanel: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params, project_token)


def _build_track_event(params: dict[str, Any], token: str) -> RequestSpec:
    distinct_id = _required(params, "distinct_id")
    event_name = _required(params, "event")
    properties = dict(params.get("properties") or {})
    properties.setdefault("token", token)
    properties.setdefault("distinct_id", distinct_id)
    payload: dict[str, Any] = {"event": event_name, "properties": properties}
    return "POST", "/track", payload, {}


def _build_engage_user(params: dict[str, Any], token: str) -> RequestSpec:
    distinct_id = _required(params, "distinct_id")
    set_verb = str(params.get("set_verb") or "$set").strip() or "$set"
    properties = dict(params.get("properties") or {})
    if not properties:
        msg = "Mixpanel: 'properties' is required for engage_user"
        raise ValueError(msg)
    payload: dict[str, Any] = {
        "$token": token,
        "$distinct_id": distinct_id,
        set_verb: properties,
    }
    return "POST", "/engage", payload, {}


def _build_update_group(params: dict[str, Any], token: str) -> RequestSpec:
    group_key = _required(params, "group_key")
    group_id = _required(params, "group_id")
    set_verb = str(params.get("set_verb") or "$set").strip() or "$set"
    properties = dict(params.get("properties") or {})
    if not properties:
        msg = "Mixpanel: 'properties' is required for update_group"
        raise ValueError(msg)
    payload: dict[str, Any] = {
        "$token": token,
        "$group_key": group_key,
        "$group_id": group_id,
        set_verb: properties,
    }
    return "POST", "/groups", payload, {}


def _build_import_events(params: dict[str, Any], token: str) -> RequestSpec:
    events = params.get("events")
    if not isinstance(events, list) or not events:
        msg = "Mixpanel: 'events' must be a non-empty list for import_events"
        raise ValueError(msg)
    normalized: list[dict[str, Any]] = []
    for raw in events:
        if not isinstance(raw, dict):
            msg = "Mixpanel: each 'events' entry must be a dict"
            raise ValueError(msg)
        event = dict(raw)
        properties = dict(event.get("properties") or {})
        properties.setdefault("token", token)
        event["properties"] = properties
        normalized.append(event)
    query: dict[str, Any] = {}
    project_id = str(params.get("project_id") or "").strip()
    if project_id:
        query["projectId"] = project_id
    return "POST", "/import", normalized, query


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Mixpanel: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any], str], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_TRACK_EVENT: _build_track_event,
    OP_ENGAGE_USER: _build_engage_user,
    OP_UPDATE_GROUP: _build_update_group,
    OP_IMPORT_EVENTS: _build_import_events,
}
