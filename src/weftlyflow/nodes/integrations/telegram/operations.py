"""Per-operation request builders for the Telegram Bot API node.

Each builder returns ``(method_name, json_body)``. The Telegram Bot API
is uniform: every call is ``POST /bot<token>/<method>`` with a JSON body.
The node layer prepends the token-bearing path prefix; this module is
purely about shaping the body.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.telegram.constants import (
    MAX_CAPTION_LENGTH,
    MAX_MESSAGE_LENGTH,
    OP_DELETE_MESSAGE,
    OP_EDIT_MESSAGE_TEXT,
    OP_GET_UPDATES,
    OP_SEND_MESSAGE,
    OP_SEND_PHOTO,
)

RequestSpec = tuple[str, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Telegram: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_send_message(params: dict[str, Any]) -> RequestSpec:
    chat_id = _required_chat_id(params)
    text = str(params.get("text") or "")
    if not text.strip():
        msg = "Telegram: 'text' is required for send_message"
        raise ValueError(msg)
    if len(text) > MAX_MESSAGE_LENGTH:
        msg = f"Telegram: 'text' must be at most {MAX_MESSAGE_LENGTH} characters"
        raise ValueError(msg)
    body: dict[str, Any] = {"chat_id": chat_id, "text": text}
    _apply_parse_mode(body, params)
    _apply_optional_bool(body, params, "disable_notification")
    _apply_optional_bool(body, params, "disable_web_page_preview")
    reply_to = params.get("reply_to_message_id")
    if reply_to not in (None, ""):
        body["reply_to_message_id"] = _coerce_positive_int(reply_to, field="reply_to_message_id")
    return "sendMessage", body


def _build_send_photo(params: dict[str, Any]) -> RequestSpec:
    chat_id = _required_chat_id(params)
    photo = str(params.get("photo") or "").strip()
    if not photo:
        msg = "Telegram: 'photo' (URL or file_id) is required for send_photo"
        raise ValueError(msg)
    body: dict[str, Any] = {"chat_id": chat_id, "photo": photo}
    caption = str(params.get("caption") or "")
    if caption:
        if len(caption) > MAX_CAPTION_LENGTH:
            msg = f"Telegram: 'caption' must be at most {MAX_CAPTION_LENGTH} characters"
            raise ValueError(msg)
        body["caption"] = caption
    _apply_parse_mode(body, params)
    _apply_optional_bool(body, params, "disable_notification")
    return "sendPhoto", body


def _build_edit_message_text(params: dict[str, Any]) -> RequestSpec:
    chat_id = _required_chat_id(params)
    message_id = params.get("message_id")
    if message_id in (None, ""):
        msg = "Telegram: 'message_id' is required for edit_message_text"
        raise ValueError(msg)
    text = str(params.get("text") or "")
    if not text.strip():
        msg = "Telegram: 'text' is required for edit_message_text"
        raise ValueError(msg)
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": _coerce_positive_int(message_id, field="message_id"),
        "text": text,
    }
    _apply_parse_mode(body, params)
    return "editMessageText", body


def _build_delete_message(params: dict[str, Any]) -> RequestSpec:
    chat_id = _required_chat_id(params)
    message_id = params.get("message_id")
    if message_id in (None, ""):
        msg = "Telegram: 'message_id' is required for delete_message"
        raise ValueError(msg)
    return "deleteMessage", {
        "chat_id": chat_id,
        "message_id": _coerce_positive_int(message_id, field="message_id"),
    }


def _build_get_updates(params: dict[str, Any]) -> RequestSpec:
    body: dict[str, Any] = {}
    offset = params.get("offset")
    if offset not in (None, ""):
        body["offset"] = _coerce_int(offset, field="offset")
    limit = params.get("limit")
    if limit not in (None, ""):
        body["limit"] = max(1, min(100, _coerce_positive_int(limit, field="limit")))
    timeout = params.get("long_poll_timeout")
    if timeout not in (None, ""):
        body["timeout"] = _coerce_positive_int(timeout, field="long_poll_timeout")
    return "getUpdates", body


def _required_chat_id(params: dict[str, Any]) -> str | int:
    raw = params.get("chat_id")
    if raw is None or raw == "":
        msg = "Telegram: 'chat_id' is required"
        raise ValueError(msg)
    if isinstance(raw, bool):
        msg = "Telegram: 'chat_id' must be a string or integer"
        raise ValueError(msg)
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if not text:
        msg = "Telegram: 'chat_id' is required"
        raise ValueError(msg)
    return text


def _apply_parse_mode(body: dict[str, Any], params: dict[str, Any]) -> None:
    parse_mode = str(params.get("parse_mode") or "").strip()
    if parse_mode:
        if parse_mode not in {"Markdown", "MarkdownV2", "HTML"}:
            msg = f"Telegram: invalid parse_mode {parse_mode!r}"
            raise ValueError(msg)
        body["parse_mode"] = parse_mode


def _apply_optional_bool(
    body: dict[str, Any],
    params: dict[str, Any],
    field: str,
) -> None:
    value = params.get(field)
    if isinstance(value, bool):
        body[field] = value


def _coerce_int(raw: Any, *, field: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Telegram: {field!r} must be an integer"
        raise ValueError(msg) from exc


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    value = _coerce_int(raw, field=field)
    if value < 1:
        msg = f"Telegram: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SEND_MESSAGE: _build_send_message,
    OP_SEND_PHOTO: _build_send_photo,
    OP_EDIT_MESSAGE_TEXT: _build_edit_message_text,
    OP_DELETE_MESSAGE: _build_delete_message,
    OP_GET_UPDATES: _build_get_updates,
}
