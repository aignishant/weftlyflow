"""Per-operation request builders for the Twitch Helix node.

Each builder returns ``(path, query_params)`` — every Helix endpoint
used here is a plain ``GET`` with query-string filters. The node layer
prepends :data:`API_BASE_URL` and attaches the dual
``Authorization: Bearer ...`` + ``Client-Id: ...`` headers.

Twitch's listing endpoints accept repeated ``id`` / ``login`` /
``user_id`` / ``user_login`` parameters — ``httpx`` serializes a list
value into a repeated ``key=`` pair which matches Helix's shape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.twitch.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    OP_GET_CHANNEL,
    OP_GET_FOLLOWERS,
    OP_GET_STREAMS,
    OP_GET_USERS,
    OP_GET_VIDEOS,
    OP_SEARCH_CHANNELS,
)

RequestSpec = tuple[str, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Twitch: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_users(params: dict[str, Any]) -> RequestSpec:
    ids = _coerce_string_list(params.get("user_ids"), field="user_ids")
    logins = _coerce_string_list(params.get("logins"), field="logins")
    if not ids and not logins:
        msg = "Twitch: get_users requires at least one of 'user_ids' or 'logins'"
        raise ValueError(msg)
    query: dict[str, Any] = {}
    if ids:
        query["id"] = ids
    if logins:
        query["login"] = logins
    return "/users", query


def _build_get_channel(params: dict[str, Any]) -> RequestSpec:
    broadcaster_id = _required(params, "broadcaster_id")
    return "/channels", {"broadcaster_id": broadcaster_id}


def _build_get_streams(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"first": _coerce_page_size(params.get("first"))}
    user_ids = _coerce_string_list(params.get("user_ids"), field="user_ids")
    if user_ids:
        query["user_id"] = user_ids
    user_logins = _coerce_string_list(params.get("user_logins"), field="user_logins")
    if user_logins:
        query["user_login"] = user_logins
    game_ids = _coerce_string_list(params.get("game_ids"), field="game_ids")
    if game_ids:
        query["game_id"] = game_ids
    language = str(params.get("language") or "").strip()
    if language:
        query["language"] = language
    cursor = str(params.get("after") or "").strip()
    if cursor:
        query["after"] = cursor
    return "/streams", query


def _build_get_videos(params: dict[str, Any]) -> RequestSpec:
    ids = _coerce_string_list(params.get("video_ids"), field="video_ids")
    user_id = str(params.get("user_id") or "").strip()
    game_id = str(params.get("game_id") or "").strip()
    if not ids and not user_id and not game_id:
        msg = "Twitch: get_videos requires one of 'video_ids', 'user_id', or 'game_id'"
        raise ValueError(msg)
    query: dict[str, Any] = {"first": _coerce_page_size(params.get("first"))}
    if ids:
        query["id"] = ids
    if user_id:
        query["user_id"] = user_id
    if game_id:
        query["game_id"] = game_id
    cursor = str(params.get("after") or "").strip()
    if cursor:
        query["after"] = cursor
    return "/videos", query


def _build_get_followers(params: dict[str, Any]) -> RequestSpec:
    broadcaster_id = _required(params, "broadcaster_id")
    query: dict[str, Any] = {
        "broadcaster_id": broadcaster_id,
        "first": _coerce_page_size(params.get("first")),
    }
    user_id = str(params.get("user_id") or "").strip()
    if user_id:
        query["user_id"] = user_id
    cursor = str(params.get("after") or "").strip()
    if cursor:
        query["after"] = cursor
    return "/channels/followers", query


def _build_search_channels(params: dict[str, Any]) -> RequestSpec:
    query_text = _required(params, "query")
    query: dict[str, Any] = {
        "query": query_text,
        "first": _coerce_page_size(params.get("first")),
    }
    live_only = params.get("live_only")
    if live_only is not None:
        query["live_only"] = _coerce_bool(live_only)
    cursor = str(params.get("after") or "").strip()
    if cursor:
        query["after"] = cursor
    return "/search/channels", query


def _coerce_page_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Twitch: 'first' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Twitch: 'first' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_SIZE)


def _coerce_bool(raw: Any) -> str:
    if isinstance(raw, bool):
        return "true" if raw else "false"
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes"}:
        return "true"
    if text in {"false", "0", "no"}:
        return "false"
    msg = f"Twitch: boolean flag must be true/false, got {raw!r}"
    raise ValueError(msg)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Twitch: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Twitch: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_USERS: _build_get_users,
    OP_GET_CHANNEL: _build_get_channel,
    OP_GET_STREAMS: _build_get_streams,
    OP_GET_VIDEOS: _build_get_videos,
    OP_GET_FOLLOWERS: _build_get_followers,
    OP_SEARCH_CHANNELS: _build_search_channels,
}
