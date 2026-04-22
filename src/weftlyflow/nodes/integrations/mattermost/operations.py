"""Per-operation request builders for the Mattermost v4 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Paths are relative to ``/api/v4`` — the node layer prepends that via
:func:`weftlyflow.credentials.types.mattermost_api.base_url_from`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.mattermost.constants import (
    OP_DELETE_POST,
    OP_GET_CHANNEL,
    OP_GET_USER_BY_USERNAME,
    OP_LIST_CHANNELS_FOR_USER,
    OP_POST_MESSAGE,
    OP_UPDATE_POST,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Mattermost: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_post_message(params: dict[str, Any]) -> RequestSpec:
    channel_id = _required(params, "channel_id")
    message = str(params.get("message") or "")
    if not message.strip():
        msg = "Mattermost: 'message' is required for post_message"
        raise ValueError(msg)
    body: dict[str, Any] = {"channel_id": channel_id, "message": message}
    root_id = str(params.get("root_id") or "").strip()
    if root_id:
        body["root_id"] = root_id
    props = params.get("props")
    if props is not None:
        if not isinstance(props, dict):
            msg = "Mattermost: 'props' must be a JSON object"
            raise ValueError(msg)
        body["props"] = props
    file_ids = _coerce_string_list(params.get("file_ids"), field="file_ids")
    if file_ids:
        body["file_ids"] = file_ids
    return "POST", "/posts", body, {}


def _build_update_post(params: dict[str, Any]) -> RequestSpec:
    post_id = _required(params, "post_id")
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "Mattermost: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    body = {**updates, "id": post_id}
    return "PUT", f"/posts/{quote(post_id, safe='')}", body, {}


def _build_delete_post(params: dict[str, Any]) -> RequestSpec:
    post_id = _required(params, "post_id")
    return "DELETE", f"/posts/{quote(post_id, safe='')}", None, {}


def _build_get_channel(params: dict[str, Any]) -> RequestSpec:
    channel_id = _required(params, "channel_id")
    return "GET", f"/channels/{quote(channel_id, safe='')}", None, {}


def _build_list_channels_for_user(params: dict[str, Any]) -> RequestSpec:
    user_id = str(params.get("user_id") or "me").strip() or "me"
    team_id = _required(params, "team_id")
    path = (
        f"/users/{quote(user_id, safe='')}"
        f"/teams/{quote(team_id, safe='')}/channels"
    )
    return "GET", path, None, {}


def _build_get_user_by_username(params: dict[str, Any]) -> RequestSpec:
    username = _required(params, "username")
    return "GET", f"/users/username/{quote(username, safe='')}", None, {}


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Mattermost: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Mattermost: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_POST_MESSAGE: _build_post_message,
    OP_UPDATE_POST: _build_update_post,
    OP_DELETE_POST: _build_delete_post,
    OP_GET_CHANNEL: _build_get_channel,
    OP_LIST_CHANNELS_FOR_USER: _build_list_channels_for_user,
    OP_GET_USER_BY_USERNAME: _build_get_user_by_username,
}
