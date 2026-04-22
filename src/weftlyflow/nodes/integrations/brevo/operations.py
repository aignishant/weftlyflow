"""Per-operation request builders for the Brevo v3 REST API node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Brevo's contact endpoints accept an email address as the path identifier
(URL-encoded), while list membership is managed via a separate
``/contacts/lists/{id}/contacts/add`` endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.brevo.constants import (
    API_VERSION_PREFIX,
    OP_ADD_CONTACT_TO_LIST,
    OP_CREATE_CONTACT,
    OP_GET_ACCOUNT,
    OP_GET_CONTACT,
    OP_SEND_EMAIL,
    OP_UPDATE_CONTACT,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Brevo: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_send_email(params: dict[str, Any]) -> RequestSpec:
    sender = _coerce_sender(params.get("sender"))
    recipients = _coerce_recipients(params.get("to"), field="to")
    subject = str(params.get("subject") or "").strip()
    html_content = str(params.get("html_content") or "")
    text_content = str(params.get("text_content") or "")
    if not subject:
        msg = "Brevo: 'subject' is required for send_email"
        raise ValueError(msg)
    if not html_content and not text_content:
        msg = "Brevo: one of 'html_content' or 'text_content' is required"
        raise ValueError(msg)
    body: dict[str, Any] = {
        "sender": sender,
        "to": recipients,
        "subject": subject,
    }
    if html_content:
        body["htmlContent"] = html_content
    if text_content:
        body["textContent"] = text_content
    reply_to = params.get("reply_to")
    if reply_to is not None and reply_to != "":
        body["replyTo"] = _coerce_sender(reply_to)
    cc = params.get("cc")
    if cc not in (None, ""):
        body["cc"] = _coerce_recipients(cc, field="cc")
    bcc = params.get("bcc")
    if bcc not in (None, ""):
        body["bcc"] = _coerce_recipients(bcc, field="bcc")
    tags = params.get("tags")
    if tags not in (None, ""):
        body["tags"] = _coerce_tags(tags)
    return "POST", f"{API_VERSION_PREFIX}/smtp/email", body, {}


def _build_create_contact(params: dict[str, Any]) -> RequestSpec:
    email = _required(params, "email")
    body: dict[str, Any] = {"email": email}
    attributes = params.get("attributes")
    if attributes is not None:
        if not isinstance(attributes, dict):
            msg = "Brevo: 'attributes' must be a JSON object"
            raise ValueError(msg)
        body["attributes"] = attributes
    list_ids = params.get("list_ids")
    if list_ids not in (None, ""):
        body["listIds"] = _coerce_int_list(list_ids, field="list_ids")
    update_enabled = params.get("update_enabled")
    if update_enabled is not None:
        body["updateEnabled"] = bool(update_enabled)
    return "POST", f"{API_VERSION_PREFIX}/contacts", body, {}


def _build_update_contact(params: dict[str, Any]) -> RequestSpec:
    email = _required(params, "email")
    body: dict[str, Any] = {}
    attributes = params.get("attributes")
    if attributes is not None:
        if not isinstance(attributes, dict):
            msg = "Brevo: 'attributes' must be a JSON object"
            raise ValueError(msg)
        body["attributes"] = attributes
    list_ids = params.get("list_ids")
    if list_ids not in (None, ""):
        body["listIds"] = _coerce_int_list(list_ids, field="list_ids")
    unlink_list_ids = params.get("unlink_list_ids")
    if unlink_list_ids not in (None, ""):
        body["unlinkListIds"] = _coerce_int_list(
            unlink_list_ids, field="unlink_list_ids",
        )
    if not body:
        msg = (
            "Brevo: update_contact needs at least one of "
            "'attributes', 'list_ids', 'unlink_list_ids'"
        )
        raise ValueError(msg)
    path = f"{API_VERSION_PREFIX}/contacts/{quote(email, safe='')}"
    return "PUT", path, body, {}


def _build_get_contact(params: dict[str, Any]) -> RequestSpec:
    email = _required(params, "email")
    path = f"{API_VERSION_PREFIX}/contacts/{quote(email, safe='')}"
    return "GET", path, None, {}


def _build_add_contact_to_list(params: dict[str, Any]) -> RequestSpec:
    list_id = _required_id(params, "list_id")
    emails_raw = params.get("emails")
    if emails_raw in (None, ""):
        msg = "Brevo: 'emails' is required for add_contact_to_list"
        raise ValueError(msg)
    emails = _coerce_email_list(emails_raw)
    path = f"{API_VERSION_PREFIX}/contacts/lists/{list_id}/contacts/add"
    return "POST", path, {"emails": emails}, {}


def _build_get_account(_: dict[str, Any]) -> RequestSpec:
    return "GET", f"{API_VERSION_PREFIX}/account", None, {}


def _coerce_sender(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        msg = "Brevo: 'sender' is required"
        raise ValueError(msg)
    if isinstance(raw, str):
        email = raw.strip()
        if not email:
            msg = "Brevo: 'sender' is required"
            raise ValueError(msg)
        return {"email": email}
    if isinstance(raw, dict):
        email = str(raw.get("email") or "").strip()
        if not email:
            msg = "Brevo: 'sender.email' is required"
            raise ValueError(msg)
        sender: dict[str, Any] = {"email": email}
        name = str(raw.get("name") or "").strip()
        if name:
            sender["name"] = name
        return sender
    msg = "Brevo: 'sender' must be a string or {email, name?} object"
    raise ValueError(msg)


def _coerce_recipients(raw: Any, *, field: str) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        msg = f"Brevo: {field!r} is required"
        raise ValueError(msg)
    if isinstance(raw, str):
        emails = [part.strip() for part in raw.split(",") if part.strip()]
        if not emails:
            msg = f"Brevo: {field!r} is empty"
            raise ValueError(msg)
        return [{"email": email} for email in emails]
    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for entry in raw:
            if isinstance(entry, str):
                email = entry.strip()
                if email:
                    out.append({"email": email})
            elif isinstance(entry, dict):
                email = str(entry.get("email") or "").strip()
                if not email:
                    msg = f"Brevo: {field!r} entry missing 'email'"
                    raise ValueError(msg)
                recipient: dict[str, Any] = {"email": email}
                name = str(entry.get("name") or "").strip()
                if name:
                    recipient["name"] = name
                out.append(recipient)
            else:
                msg = f"Brevo: {field!r} entries must be strings or objects"
                raise ValueError(msg)
        if not out:
            msg = f"Brevo: {field!r} is empty"
            raise ValueError(msg)
        return out
    msg = f"Brevo: {field!r} must be a string, list, or object"
    raise ValueError(msg)


def _coerce_email_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        emails = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        emails = [str(part).strip() for part in raw if str(part).strip()]
    else:
        msg = "Brevo: 'emails' must be a string or list of strings"
        raise ValueError(msg)
    if not emails:
        msg = "Brevo: 'emails' is empty"
        raise ValueError(msg)
    return emails


def _coerce_tags(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = "Brevo: 'tags' must be a string or list of strings"
    raise ValueError(msg)


def _coerce_int_list(raw: Any, *, field: str) -> list[int]:
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        items = [str(part).strip() for part in raw if str(part).strip()]
    else:
        msg = f"Brevo: {field!r} must be a string, list, or integer"
        raise ValueError(msg)
    out: list[int] = []
    for item in items:
        try:
            out.append(int(item))
        except (TypeError, ValueError) as exc:
            msg = f"Brevo: {field!r} entries must be integers"
            raise ValueError(msg) from exc
    return out


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Brevo: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_id(params: dict[str, Any], key: str) -> str:
    raw = params.get(key)
    if raw is None or raw == "":
        msg = f"Brevo: {key!r} is required"
        raise ValueError(msg)
    try:
        numeric = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Brevo: {key!r} must be an integer"
        raise ValueError(msg) from exc
    if numeric < 1:
        msg = f"Brevo: {key!r} must be >= 1"
        raise ValueError(msg)
    return str(numeric)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SEND_EMAIL: _build_send_email,
    OP_CREATE_CONTACT: _build_create_contact,
    OP_UPDATE_CONTACT: _build_update_contact,
    OP_GET_CONTACT: _build_get_contact,
    OP_ADD_CONTACT_TO_LIST: _build_add_contact_to_list,
    OP_GET_ACCOUNT: _build_get_account,
}
