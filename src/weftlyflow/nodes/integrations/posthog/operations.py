"""Per-operation request builders for the PostHog node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to the PostHog host (default ``https://us.i.posthog.com``).

Distinctive PostHog shape:

* Every ingestion path — ``/capture``, ``/batch``, and the
  ``/capture``-via-``$identify``/``$create_alias`` variants — carries
  the **project API key inside the JSON body** under the ``api_key``
  field, alongside event data. No other node in the catalog folds
  credential material into the body.
* The ``api_key`` insertion happens in the node (not here) so the
  builders stay a pure body-shaping layer and tests exercising body
  content can introspect without reaching for credential fixtures.
* ``batch`` additionally wraps the events in a top-level ``{"batch":
  [...], "api_key": "..."}`` envelope. ``identify``/``alias`` are
  ``/capture`` calls with the reserved ``$identify`` /
  ``$create_alias`` event names.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.posthog.constants import (
    OP_ALIAS,
    OP_BATCH,
    OP_CAPTURE,
    OP_DECIDE,
    OP_IDENTIFY,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"PostHog: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_capture(params: dict[str, Any]) -> RequestSpec:
    body = _event_payload(
        event=_required(params, "event"),
        distinct_id=_required(params, "distinct_id"),
        properties=params.get("properties"),
        timestamp=params.get("timestamp"),
    )
    return "POST", "/capture/", body, {}


def _build_identify(params: dict[str, Any]) -> RequestSpec:
    properties = dict(params.get("properties") or {})
    set_traits = params.get("set")
    if isinstance(set_traits, dict) and set_traits:
        properties["$set"] = dict(set_traits)
    set_once = params.get("set_once")
    if isinstance(set_once, dict) and set_once:
        properties["$set_once"] = dict(set_once)
    body = _event_payload(
        event="$identify",
        distinct_id=_required(params, "distinct_id"),
        properties=properties,
        timestamp=params.get("timestamp"),
    )
    return "POST", "/capture/", body, {}


def _build_alias(params: dict[str, Any]) -> RequestSpec:
    properties = dict(params.get("properties") or {})
    properties["distinct_id"] = _required(params, "distinct_id")
    properties["alias"] = _required(params, "alias")
    body = _event_payload(
        event="$create_alias",
        distinct_id=properties["distinct_id"],
        properties=properties,
        timestamp=params.get("timestamp"),
    )
    return "POST", "/capture/", body, {}


def _build_batch(params: dict[str, Any]) -> RequestSpec:
    events = params.get("events")
    if not isinstance(events, list) or not events:
        msg = "PostHog: 'events' must be a non-empty list for batch"
        raise ValueError(msg)
    normalized: list[dict[str, Any]] = []
    for raw in events:
        if not isinstance(raw, dict):
            msg = "PostHog: each 'events' entry must be a dict"
            raise ValueError(msg)
        normalized.append(dict(raw))
    return "POST", "/batch/", {"batch": normalized}, {}


def _build_decide(params: dict[str, Any]) -> RequestSpec:
    distinct_id = _required(params, "distinct_id")
    body: dict[str, Any] = {"distinct_id": distinct_id}
    groups = params.get("groups")
    if isinstance(groups, dict) and groups:
        body["groups"] = dict(groups)
    person_properties = params.get("person_properties")
    if isinstance(person_properties, dict) and person_properties:
        body["person_properties"] = dict(person_properties)
    return "POST", "/decide/?v=3", body, {}


def _event_payload(
    *,
    event: str,
    distinct_id: str,
    properties: Any,
    timestamp: Any,
) -> dict[str, Any]:
    merged_properties: dict[str, Any] = {}
    if isinstance(properties, dict):
        merged_properties.update(properties)
    merged_properties.setdefault("distinct_id", distinct_id)
    body: dict[str, Any] = {
        "event": event,
        "distinct_id": distinct_id,
        "properties": merged_properties,
    }
    if isinstance(timestamp, str) and timestamp.strip():
        body["timestamp"] = timestamp.strip()
    return body


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"PostHog: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CAPTURE: _build_capture,
    OP_IDENTIFY: _build_identify,
    OP_ALIAS: _build_alias,
    OP_BATCH: _build_batch,
    OP_DECIDE: _build_decide,
}
