"""Per-operation request builders for the Gmail node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://gmail.googleapis.com/gmail/v1/users/me``.

Distinctive Gmail shape:

* **``send_message``** builds an RFC 2822 MIME message in-process and
  encodes the whole thing as **base64url** (not plain base64) in the
  ``raw`` field of a JSON body — ``{"raw": "..."}``. No other Google
  API in the catalog carries an email envelope this way; Gmail chose
  this shape so clients can pre-build the MIME (attachments included)
  without the API needing to parse the ``To:/From:/Subject:`` tuple
  themselves.
* **``add_label``** targets the ``modify`` endpoint, which accepts
  both add and remove label arrays in one round-trip.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.gmail.constants import (
    GMAIL_API_PREFIX,
    OP_ADD_LABEL,
    OP_GET_MESSAGE,
    OP_LIST_MESSAGES,
    OP_SEND_MESSAGE,
    OP_TRASH_MESSAGE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Gmail: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def build_raw_message(
    *,
    to: str,
    subject: str,
    body_text: str,
    cc: str = "",
    bcc: str = "",
    from_address: str = "",
) -> str:
    """Return the ``raw`` field value: base64url(RFC2822 MIME).

    Example:
        >>> raw = build_raw_message(to="a@b.c", subject="hi", body_text="yo")
        >>> base64.urlsafe_b64decode(raw + "==").startswith(b"To: a@b.c")
        True
    """
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    if from_address:
        msg["From"] = from_address
    msg.set_content(body_text)
    return base64.urlsafe_b64encode(bytes(msg)).rstrip(b"=").decode("ascii")


def _build_send_message(params: dict[str, Any]) -> RequestSpec:
    raw = str(params.get("raw") or "").strip()
    if not raw:
        to = _required(params, "to")
        subject = _required(params, "subject")
        body_text = str(params.get("body") or "").strip()
        if not body_text:
            msg = "Gmail: either 'raw' or 'body' must be supplied for send_message"
            raise ValueError(msg)
        raw = build_raw_message(
            to=to,
            subject=subject,
            body_text=body_text,
            cc=str(params.get("cc") or ""),
            bcc=str(params.get("bcc") or ""),
            from_address=str(params.get("from") or ""),
        )
    body: dict[str, Any] = {"raw": raw}
    thread_id = str(params.get("thread_id") or "").strip()
    if thread_id:
        body["threadId"] = thread_id
    return "POST", f"{GMAIL_API_PREFIX}/messages/send", body, {}


def _build_list_messages(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    for key in ("q", "labelIds", "pageToken", "maxResults", "includeSpamTrash"):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = _stringify(value)
    return "GET", f"{GMAIL_API_PREFIX}/messages", None, query


def _build_get_message(params: dict[str, Any]) -> RequestSpec:
    message_id = _required(params, "message_id")
    query: dict[str, Any] = {}
    fmt = str(params.get("format") or "").strip()
    if fmt:
        query["format"] = fmt
    path = f"{GMAIL_API_PREFIX}/messages/{quote(message_id, safe='')}"
    return "GET", path, None, query


def _build_trash_message(params: dict[str, Any]) -> RequestSpec:
    message_id = _required(params, "message_id")
    path = f"{GMAIL_API_PREFIX}/messages/{quote(message_id, safe='')}/trash"
    return "POST", path, None, {}


def _build_add_label(params: dict[str, Any]) -> RequestSpec:
    message_id = _required(params, "message_id")
    add_label_ids = params.get("add_label_ids")
    remove_label_ids = params.get("remove_label_ids")
    body: dict[str, Any] = {}
    if isinstance(add_label_ids, list) and add_label_ids:
        body["addLabelIds"] = [str(value) for value in add_label_ids]
    if isinstance(remove_label_ids, list) and remove_label_ids:
        body["removeLabelIds"] = [str(value) for value in remove_label_ids]
    if not body:
        msg = "Gmail: add_label requires 'add_label_ids' or 'remove_label_ids'"
        raise ValueError(msg)
    path = f"{GMAIL_API_PREFIX}/messages/{quote(message_id, safe='')}/modify"
    return "POST", path, body, {}


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Gmail: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SEND_MESSAGE: _build_send_message,
    OP_LIST_MESSAGES: _build_list_messages,
    OP_GET_MESSAGE: _build_get_message,
    OP_TRASH_MESSAGE: _build_trash_message,
    OP_ADD_LABEL: _build_add_label,
}
