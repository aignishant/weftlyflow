"""Per-operation request builders for the DocuSign eSignature node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to the ``account_base_url`` stored on the credential (e.g.
``https://demo.docusign.net/restapi``). The account ID is interpolated
into each path — DocuSign scopes every REST call to one account.

Auth is a runtime-fetched Bearer, so builders deal only with URL
shape and body content.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.docusign.constants import (
    OP_CREATE_ENVELOPE,
    OP_GET_ENVELOPE,
    OP_LIST_ENVELOPES,
    OP_LIST_TEMPLATES,
    STATUS_CREATED,
    STATUS_SENT,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, str]]

_VALID_STATUSES: frozenset[str] = frozenset({STATUS_SENT, STATUS_CREATED})


def build_request(
    operation: str, account_id: str, params: dict[str, Any],
) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    if not account_id.strip():
        msg = "DocuSign: account_id is required"
        raise ValueError(msg)
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"DocuSign: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(account_id.strip(), params)


def _build_list_envelopes(account_id: str, params: dict[str, Any]) -> RequestSpec:
    query: dict[str, str] = {}
    from_date = str(params.get("from_date") or "").strip()
    if from_date:
        query["from_date"] = from_date
    status = str(params.get("status") or "").strip().lower()
    if status:
        query["status"] = status
    return "GET", f"/v2.1/accounts/{account_id}/envelopes", None, query


def _build_get_envelope(account_id: str, params: dict[str, Any]) -> RequestSpec:
    envelope_id = _required_str(params, "envelope_id")
    return (
        "GET",
        f"/v2.1/accounts/{account_id}/envelopes/{envelope_id}",
        None,
        {},
    )


def _build_create_envelope(account_id: str, params: dict[str, Any]) -> RequestSpec:
    email_subject = _required_str(params, "email_subject")
    status = str(params.get("status") or STATUS_SENT).strip().lower()
    if status not in _VALID_STATUSES:
        msg = (
            f"DocuSign: 'status' must be one of {sorted(_VALID_STATUSES)!r} — "
            f"got {status!r}"
        )
        raise ValueError(msg)
    template_id = str(params.get("template_id") or "").strip()
    body: dict[str, Any] = {
        "emailSubject": email_subject,
        "status": status,
    }
    message = str(params.get("email_message") or "").strip()
    if message:
        body["emailBlurb"] = message
    if template_id:
        body["templateId"] = template_id
        template_roles = params.get("template_roles")
        if isinstance(template_roles, list) and template_roles:
            body["templateRoles"] = template_roles
    else:
        documents = params.get("documents")
        if not isinstance(documents, list) or not documents:
            msg = (
                "DocuSign: create_envelope requires 'template_id' or a non-empty "
                "'documents' list"
            )
            raise ValueError(msg)
        body["documents"] = documents
        recipients = params.get("recipients")
        if isinstance(recipients, dict):
            body["recipients"] = recipients
    return "POST", f"/v2.1/accounts/{account_id}/envelopes", body, {}


def _build_list_templates(account_id: str, _params: dict[str, Any]) -> RequestSpec:
    return "GET", f"/v2.1/accounts/{account_id}/templates", None, {}


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"DocuSign: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[str, dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_ENVELOPES: _build_list_envelopes,
    OP_GET_ENVELOPE: _build_get_envelope,
    OP_CREATE_ENVELOPE: _build_create_envelope,
    OP_LIST_TEMPLATES: _build_list_templates,
}
