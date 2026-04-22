"""Per-operation request builders for the Twilio Programmable Messaging node.

Each builder returns ``(http_method, path, form_fields, query_params)``.
Twilio expects **form-encoded** bodies (not JSON), so send ops return a
list of form fields rather than a JSON dict. The node layer URL-encodes
them and sets ``Content-Type: application/x-www-form-urlencoded`` per
Twilio's docs.

Paths are relative to ``/2010-04-01/Accounts/{AccountSid}/`` — the node
layer prepends that prefix so the Account SID lives with the credential.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.twilio.constants import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    OP_DELETE_MESSAGE,
    OP_GET_MESSAGE,
    OP_LIST_MESSAGES,
    OP_SEND_SMS,
)

RequestSpec = tuple[str, str, list[tuple[str, str]] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Twilio: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_send_sms(params: dict[str, Any]) -> RequestSpec:
    to = _required(params, "to")
    body = _required(params, "body")
    from_number = str(params.get("from") or "").strip()
    messaging_service_sid = str(params.get("messaging_service_sid") or "").strip()
    if not from_number and not messaging_service_sid:
        msg = "Twilio: either 'from' or 'messaging_service_sid' is required"
        raise ValueError(msg)
    fields: list[tuple[str, str]] = [("To", to), ("Body", body)]
    if from_number:
        fields.append(("From", from_number))
    if messaging_service_sid:
        fields.append(("MessagingServiceSid", messaging_service_sid))
    media_urls = _coerce_string_list(params.get("media_urls"), field="media_urls")
    fields.extend(("MediaUrl", url) for url in media_urls)
    return "POST", "Messages.json", fields, {}


def _build_get_message(params: dict[str, Any]) -> RequestSpec:
    sid = _required(params, "message_sid")
    path = f"Messages/{quote(sid, safe='')}.json"
    return "GET", path, None, {}


def _build_list_messages(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"PageSize": _coerce_limit(params.get("page_size"))}
    to = str(params.get("to") or "").strip()
    if to:
        query["To"] = to
    from_number = str(params.get("from") or "").strip()
    if from_number:
        query["From"] = from_number
    date_sent = str(params.get("date_sent") or "").strip()
    if date_sent:
        query["DateSent"] = date_sent
    return "GET", "Messages.json", None, query


def _build_delete_message(params: dict[str, Any]) -> RequestSpec:
    sid = _required(params, "message_sid")
    path = f"Messages/{quote(sid, safe='')}.json"
    return "DELETE", path, None, {}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Twilio: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Twilio: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Twilio: 'page_size' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Twilio: 'page_size' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SEND_SMS: _build_send_sms,
    OP_GET_MESSAGE: _build_get_message,
    OP_LIST_MESSAGES: _build_list_messages,
    OP_DELETE_MESSAGE: _build_delete_message,
}
