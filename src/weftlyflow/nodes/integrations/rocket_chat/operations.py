"""Per-operation request builders for the Rocket.Chat node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``<base_url>`` (credential-owned, self-hosted servers).

Distinctive Rocket.Chat shapes:

* ``chat.postMessage`` / ``chat.update`` require ``roomId`` and
  ``text`` in the JSON body — not query params.
* ``channels.create`` takes ``name`` and optional ``members`` array;
  the server returns 400 on duplicate name.
* List endpoints use camelCase query params (``offset``, ``count``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.rocket_chat.constants import (
    OP_CREATE_CHANNEL,
    OP_DELETE_MESSAGE,
    OP_GET_USER,
    OP_LIST_CHANNELS,
    OP_POST_MESSAGE,
    OP_UPDATE_MESSAGE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Rocket.Chat: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_post_message(params: dict[str, Any]) -> RequestSpec:
    room_id = _required(params, "room_id")
    text = _required(params, "text")
    body: dict[str, Any] = {"roomId": room_id, "text": text}
    alias = str(params.get("alias") or "").strip()
    if alias:
        body["alias"] = alias
    emoji = str(params.get("emoji") or "").strip()
    if emoji:
        body["emoji"] = emoji
    avatar = str(params.get("avatar") or "").strip()
    if avatar:
        body["avatar"] = avatar
    attachments = params.get("attachments")
    if isinstance(attachments, list) and attachments:
        body["attachments"] = attachments
    return "POST", "/api/v1/chat.postMessage", body, {}


def _build_update_message(params: dict[str, Any]) -> RequestSpec:
    room_id = _required(params, "room_id")
    msg_id = _required(params, "message_id")
    text = _required(params, "text")
    body: dict[str, Any] = {"roomId": room_id, "msgId": msg_id, "text": text}
    return "POST", "/api/v1/chat.update", body, {}


def _build_delete_message(params: dict[str, Any]) -> RequestSpec:
    room_id = _required(params, "room_id")
    msg_id = _required(params, "message_id")
    body: dict[str, Any] = {"roomId": room_id, "msgId": msg_id}
    as_user = params.get("as_user")
    if isinstance(as_user, bool):
        body["asUser"] = as_user
    return "POST", "/api/v1/chat.delete", body, {}


def _build_list_channels(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    for src, dst in (("count", "count"), ("offset", "offset"), ("sort", "sort")):
        value = params.get(src)
        if value not in (None, ""):
            query[dst] = _stringify(value)
    return "GET", "/api/v1/channels.list", None, query


def _build_create_channel(params: dict[str, Any]) -> RequestSpec:
    name = _required(params, "name")
    body: dict[str, Any] = {"name": name}
    members = params.get("members")
    if isinstance(members, list) and members:
        body["members"] = [str(m) for m in members]
    read_only = params.get("read_only")
    if isinstance(read_only, bool):
        body["readOnly"] = read_only
    return "POST", "/api/v1/channels.create", body, {}


def _build_get_user(params: dict[str, Any]) -> RequestSpec:
    user_id = str(params.get("user_id") or "").strip()
    username = str(params.get("username") or "").strip()
    if not user_id and not username:
        msg = "Rocket.Chat: one of 'user_id' or 'username' is required"
        raise ValueError(msg)
    query: dict[str, Any] = {}
    if user_id:
        query["userId"] = user_id
    else:
        query["username"] = username
    return "GET", "/api/v1/users.info", None, query


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Rocket.Chat: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_POST_MESSAGE: _build_post_message,
    OP_UPDATE_MESSAGE: _build_update_message,
    OP_DELETE_MESSAGE: _build_delete_message,
    OP_LIST_CHANNELS: _build_list_channels,
    OP_CREATE_CHANNEL: _build_create_channel,
    OP_GET_USER: _build_get_user,
}
