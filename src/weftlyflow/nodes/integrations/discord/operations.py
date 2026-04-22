"""Per-operation request builders for the Discord node.

Each builder returns ``(http_method, path, json_body)``. ``json_body`` is
``None`` for GET/DELETE requests. Validation happens here; the dispatcher
only handles IO.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.discord.constants import (
    API_VERSION_PREFIX,
    MAX_CONTENT_LENGTH,
    OP_DELETE_MESSAGE,
    OP_EDIT_MESSAGE,
    OP_GET_CHANNEL,
    OP_SEND_MESSAGE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Discord: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_send_message(params: dict[str, Any]) -> RequestSpec:
    channel_id = _required(params, "channel_id")
    body = _message_body(params, require_body=True)
    path = f"{API_VERSION_PREFIX}/channels/{channel_id}/messages"
    return "POST", path, body


def _build_get_channel(params: dict[str, Any]) -> RequestSpec:
    channel_id = _required(params, "channel_id")
    return "GET", f"{API_VERSION_PREFIX}/channels/{channel_id}", None


def _build_edit_message(params: dict[str, Any]) -> RequestSpec:
    channel_id = _required(params, "channel_id")
    message_id = _required(params, "message_id")
    body = _message_body(params, require_body=True)
    path = f"{API_VERSION_PREFIX}/channels/{channel_id}/messages/{message_id}"
    return "PATCH", path, body


def _build_delete_message(params: dict[str, Any]) -> RequestSpec:
    channel_id = _required(params, "channel_id")
    message_id = _required(params, "message_id")
    path = f"{API_VERSION_PREFIX}/channels/{channel_id}/messages/{message_id}"
    return "DELETE", path, None


def _message_body(params: dict[str, Any], *, require_body: bool) -> dict[str, Any]:
    body: dict[str, Any] = {}
    content = str(params.get("content") or "").strip()
    if content:
        if len(content) > MAX_CONTENT_LENGTH:
            msg = f"Discord: 'content' exceeds {MAX_CONTENT_LENGTH} characters"
            raise ValueError(msg)
        body["content"] = content
    embeds = params.get("embeds")
    if embeds is not None:
        if not isinstance(embeds, list):
            msg = "Discord: 'embeds' must be a list"
            raise ValueError(msg)
        body["embeds"] = [dict(e) for e in embeds if isinstance(e, dict)]
    if require_body and not body:
        msg = "Discord: at least one of 'content' or 'embeds' is required"
        raise ValueError(msg)
    tts = params.get("tts")
    if isinstance(tts, bool):
        body["tts"] = tts
    return body


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Discord: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SEND_MESSAGE: _build_send_message,
    OP_GET_CHANNEL: _build_get_channel,
    OP_EDIT_MESSAGE: _build_edit_message,
    OP_DELETE_MESSAGE: _build_delete_message,
}
