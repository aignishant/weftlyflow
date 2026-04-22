"""Per-operation form-body builders for the Pushover node.

Each builder returns ``(path, form_fields)`` — the node layer merges in
the ``token`` + ``user`` pair from the credential and POSTs the combined
form to ``https://api.pushover.net/1<path>``.

Pushover caps every free-form text field at a service-defined byte
length; exceeding the cap yields an HTTP 400 from the server. We
enforce the same caps client-side so workflow authors get a clean
ValueError instead.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.pushover.constants import (
    EMERGENCY_PRIORITY,
    GLANCE_SUBTEXT_MAX_LENGTH,
    GLANCE_TEXT_MAX_LENGTH,
    MAX_EXPIRE_SECONDS,
    MAX_PRIORITY,
    MESSAGE_MAX_LENGTH,
    MIN_PRIORITY,
    MIN_RETRY_SECONDS,
    OP_SEND_GLANCE,
    OP_SEND_NOTIFICATION,
    TITLE_MAX_LENGTH,
    URL_MAX_LENGTH,
    URL_TITLE_MAX_LENGTH,
)

FormSpec = tuple[str, dict[str, str]]


def build_request(operation: str, params: dict[str, Any]) -> FormSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Pushover: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_send_notification(params: dict[str, Any]) -> FormSpec:
    message = _required_text(params, "message", MESSAGE_MAX_LENGTH)
    form: dict[str, str] = {"message": message}
    title = _optional_text(params.get("title"), "title", TITLE_MAX_LENGTH)
    if title:
        form["title"] = title
    url = _optional_text(params.get("url"), "url", URL_MAX_LENGTH)
    if url:
        form["url"] = url
    url_title = _optional_text(
        params.get("url_title"), "url_title", URL_TITLE_MAX_LENGTH,
    )
    if url_title:
        form["url_title"] = url_title
    priority = params.get("priority")
    if priority not in (None, ""):
        priority_int = _coerce_priority(priority)
        form["priority"] = str(priority_int)
        if priority_int == EMERGENCY_PRIORITY:
            form["retry"] = str(_coerce_retry(params.get("retry")))
            form["expire"] = str(_coerce_expire(params.get("expire")))
    sound = _optional_text(params.get("sound"), "sound", max_length=50)
    if sound:
        form["sound"] = sound
    device = _optional_text(params.get("device"), "device", max_length=100)
    if device:
        form["device"] = device
    html = params.get("html")
    if html is not None and bool(html):
        form["html"] = "1"
    return "/messages.json", form


def _build_send_glance(params: dict[str, Any]) -> FormSpec:
    form: dict[str, str] = {}
    text = _optional_text(params.get("text"), "text", GLANCE_TEXT_MAX_LENGTH)
    if text:
        form["text"] = text
    subtext = _optional_text(
        params.get("subtext"), "subtext", GLANCE_SUBTEXT_MAX_LENGTH,
    )
    if subtext:
        form["subtext"] = subtext
    title = _optional_text(params.get("title"), "title", GLANCE_TEXT_MAX_LENGTH)
    if title:
        form["title"] = title
    count = params.get("count")
    if count not in (None, ""):
        form["count"] = str(_coerce_int(count, field="count"))
    percent = params.get("percent")
    if percent not in (None, ""):
        value = _coerce_int(percent, field="percent")
        if not 0 <= value <= 100:  # noqa: PLR2004
            msg = "Pushover: 'percent' must be in [0, 100]"
            raise ValueError(msg)
        form["percent"] = str(value)
    device = _optional_text(params.get("device"), "device", max_length=100)
    if device:
        form["device"] = device
    if not form:
        msg = "Pushover: send_glance requires at least one updatable field"
        raise ValueError(msg)
    return "/glances.json", form


def _required_text(params: dict[str, Any], key: str, max_length: int) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Pushover: {key!r} is required"
        raise ValueError(msg)
    if len(value) > max_length:
        msg = f"Pushover: {key!r} exceeds {max_length}-character cap"
        raise ValueError(msg)
    return value


def _optional_text(raw: Any, key: str, max_length: int) -> str:
    if raw in (None, ""):
        return ""
    value = str(raw).strip()
    if len(value) > max_length:
        msg = f"Pushover: {key!r} exceeds {max_length}-character cap"
        raise ValueError(msg)
    return value


def _coerce_priority(raw: Any) -> int:
    value = _coerce_int(raw, field="priority")
    if not MIN_PRIORITY <= value <= MAX_PRIORITY:
        msg = f"Pushover: 'priority' must be in [{MIN_PRIORITY}, {MAX_PRIORITY}]"
        raise ValueError(msg)
    return value


def _coerce_retry(raw: Any) -> int:
    if raw in (None, ""):
        msg = "Pushover: emergency priority requires 'retry' (>= 30)"
        raise ValueError(msg)
    value = _coerce_int(raw, field="retry")
    if value < MIN_RETRY_SECONDS:
        msg = f"Pushover: 'retry' must be >= {MIN_RETRY_SECONDS} seconds"
        raise ValueError(msg)
    return value


def _coerce_expire(raw: Any) -> int:
    if raw in (None, ""):
        msg = f"Pushover: emergency priority requires 'expire' (<= {MAX_EXPIRE_SECONDS})"
        raise ValueError(msg)
    value = _coerce_int(raw, field="expire")
    if value < 1 or value > MAX_EXPIRE_SECONDS:
        msg = f"Pushover: 'expire' must be in [1, {MAX_EXPIRE_SECONDS}]"
        raise ValueError(msg)
    return value


def _coerce_int(raw: Any, *, field: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Pushover: {field!r} must be an integer"
        raise ValueError(msg) from exc


_Builder = Callable[[dict[str, Any]], FormSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SEND_NOTIFICATION: _build_send_notification,
    OP_SEND_GLANCE: _build_send_glance,
}
