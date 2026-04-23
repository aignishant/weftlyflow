"""Per-operation request builders for the Segment node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://api.segment.io``.

Distinctive Segment shape:

* Every verb — ``track``/``identify``/``group``/``page``/``alias`` —
  POSTs to ``/v1/<verb>`` with a JSON body whose shape is specific to
  the verb. ``userId`` OR ``anonymousId`` is required on every call;
  Segment rejects payloads that carry neither.
* ``track`` requires ``event``; ``group`` requires ``groupId``;
  ``alias`` requires ``previousId``. Validation happens here so a
  missing field raises :class:`ValueError` *before* the network call.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.segment.constants import (
    OP_ALIAS,
    OP_GROUP,
    OP_IDENTIFY,
    OP_PAGE,
    OP_TRACK,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Segment: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_track(params: dict[str, Any]) -> RequestSpec:
    body = _identity_envelope(params)
    body["event"] = _required(params, "event")
    _maybe_copy(body, params, "properties", dict)
    _maybe_copy(body, params, "context", dict)
    _maybe_copy(body, params, "timestamp", str)
    return "POST", "/v1/track", body, {}


def _build_identify(params: dict[str, Any]) -> RequestSpec:
    body = _identity_envelope(params)
    _maybe_copy(body, params, "traits", dict)
    _maybe_copy(body, params, "context", dict)
    _maybe_copy(body, params, "timestamp", str)
    return "POST", "/v1/identify", body, {}


def _build_group(params: dict[str, Any]) -> RequestSpec:
    body = _identity_envelope(params)
    body["groupId"] = _required(params, "groupId")
    _maybe_copy(body, params, "traits", dict)
    _maybe_copy(body, params, "context", dict)
    _maybe_copy(body, params, "timestamp", str)
    return "POST", "/v1/group", body, {}


def _build_page(params: dict[str, Any]) -> RequestSpec:
    body = _identity_envelope(params)
    _maybe_copy(body, params, "name", str)
    _maybe_copy(body, params, "category", str)
    _maybe_copy(body, params, "properties", dict)
    _maybe_copy(body, params, "context", dict)
    _maybe_copy(body, params, "timestamp", str)
    return "POST", "/v1/page", body, {}


def _build_alias(params: dict[str, Any]) -> RequestSpec:
    body: dict[str, Any] = {}
    body["userId"] = _required(params, "userId")
    body["previousId"] = _required(params, "previousId")
    _maybe_copy(body, params, "context", dict)
    _maybe_copy(body, params, "timestamp", str)
    return "POST", "/v1/alias", body, {}


def _identity_envelope(params: dict[str, Any]) -> dict[str, Any]:
    user_id = str(params.get("userId") or "").strip()
    anon_id = str(params.get("anonymousId") or "").strip()
    if not user_id and not anon_id:
        msg = "Segment: 'userId' or 'anonymousId' is required"
        raise ValueError(msg)
    body: dict[str, Any] = {}
    if user_id:
        body["userId"] = user_id
    if anon_id:
        body["anonymousId"] = anon_id
    return body


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Segment: {key!r} is required"
        raise ValueError(msg)
    return value


def _maybe_copy(
    body: dict[str, Any],
    params: dict[str, Any],
    key: str,
    expected: type,
) -> None:
    value = params.get(key)
    if value in (None, ""):
        return
    if expected is str:
        body[key] = str(value)
    elif expected is dict and isinstance(value, dict):
        body[key] = dict(value)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_TRACK: _build_track,
    OP_IDENTIFY: _build_identify,
    OP_GROUP: _build_group,
    OP_PAGE: _build_page,
    OP_ALIAS: _build_alias,
}
