"""SendGrid node — send a transactional email via the v3 Mail Send API.

The node posts one email per input item to
``https://api.sendgrid.com/v3/mail/send`` with
``Authorization: Bearer <api_key>`` from a
:class:`~weftlyflow.credentials.types.bearer_token.BearerTokenCredential`
(the ``token`` field holds the SendGrid API key, which typically starts
with ``SG.``).

Parameters (all expression-capable):

* ``operation`` — currently only ``send_email``.
* ``from_email`` / ``from_name`` — sender identity. Falls back to the
  ``default_from_email`` / ``default_from_name`` values on the credential
  payload when the node parameter is blank.
* ``to`` — comma-separated list of recipient addresses (or a real list).
* ``subject`` — email subject line.
* ``text`` / ``html`` — message body. At least one must be present.
* ``cc`` / ``bcc`` — optional recipient lists.
* ``reply_to`` — optional Reply-To address.

Output: one item per input item with ``operation``, ``status``,
``message_id`` (from the ``X-Message-Id`` response header), and ``ok``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.integrations.sendgrid.constants import (
    API_BASE_URL,
    CONTENT_TYPE_HTML,
    CONTENT_TYPE_TEXT,
    DEFAULT_TIMEOUT_SECONDS,
    MAIL_SEND_ENDPOINT,
    OP_SEND_EMAIL,
    SUPPORTED_OPERATIONS,
)

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "sendgrid_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.bearer_token",)

log = structlog.get_logger(__name__)


class SendGridNode(BaseNode):
    """Send a transactional email per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.sendgrid",
        version=1,
        display_name="SendGrid",
        description="Send transactional email via SendGrid's v3 Mail Send API.",
        icon="icons/sendgrid.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "email"],
        documentation_url="https://docs.sendgrid.com/api-reference/mail-send/mail-send",
        credentials=[
            CredentialSlot(
                name=_CREDENTIAL_SLOT,
                required=True,
                credential_types=list(_CREDENTIAL_SLUGS),
            ),
        ],
        properties=[
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=OP_SEND_EMAIL,
                required=True,
                options=[PropertyOption(value=OP_SEND_EMAIL, label="Send Email")],
            ),
            PropertySchema(
                name="from_email",
                display_name="From Email",
                type="string",
                description="Falls back to the credential's default_from_email.",
            ),
            PropertySchema(
                name="from_name",
                display_name="From Name",
                type="string",
            ),
            PropertySchema(
                name="to",
                display_name="To",
                type="string",
                required=True,
                description="Comma-separated recipient addresses (or a list).",
            ),
            PropertySchema(
                name="cc",
                display_name="Cc",
                type="string",
            ),
            PropertySchema(
                name="bcc",
                display_name="Bcc",
                type="string",
            ),
            PropertySchema(
                name="reply_to",
                display_name="Reply-To",
                type="string",
            ),
            PropertySchema(
                name="subject",
                display_name="Subject",
                type="string",
                required=True,
            ),
            PropertySchema(
                name="text",
                display_name="Plain Text Body",
                type="string",
            ),
            PropertySchema(
                name="html",
                display_name="HTML Body",
                type="string",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one SendGrid send per input item."""
        api_key, default_from_email, default_from_name = await _resolve_credential(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        api_key=api_key,
                        default_from_email=default_from_email,
                        default_from_name=default_from_name,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credential(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "SendGrid: a bearer-token credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    api_key = str(payload.get("token") or "").strip()
    if not api_key:
        msg = "SendGrid: credential has an empty 'token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    default_from_email = str(payload.get("default_from_email") or "").strip()
    default_from_name = str(payload.get("default_from_name") or "").strip()
    return api_key, default_from_email, default_from_name


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    default_from_email: str,
    default_from_name: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEND_EMAIL).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"SendGrid: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        body = _build_mail_body(
            params,
            default_from_email=default_from_email,
            default_from_name=default_from_name,
        )
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.post(
            MAIL_SEND_ENDPOINT,
            json=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("sendgrid.request_failed", error=str(exc))
        msg = f"SendGrid: network error sending email: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    ok = response.status_code in (httpx.codes.OK, httpx.codes.ACCEPTED)
    message_id = response.headers.get("X-Message-Id", "")
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "ok": ok,
        "message_id": message_id,
    }
    if not ok:
        error = _error_message(response)
        logger.warning("sendgrid.api_error", status=response.status_code, error=error)
        msg = f"SendGrid send_email failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("sendgrid.ok", status=response.status_code)
    return Item(json=result)


def _build_mail_body(
    params: dict[str, Any],
    *,
    default_from_email: str,
    default_from_name: str,
) -> dict[str, Any]:
    from_email = str(params.get("from_email") or "").strip() or default_from_email
    if not from_email:
        msg = "SendGrid: 'from_email' is required (or set default_from_email on the credential)"
        raise ValueError(msg)
    from_name = str(params.get("from_name") or "").strip() or default_from_name
    subject = str(params.get("subject") or "").strip()
    if not subject:
        msg = "SendGrid: 'subject' is required"
        raise ValueError(msg)
    to_list = _coerce_addresses(params.get("to"), field="to")
    if not to_list:
        msg = "SendGrid: 'to' must contain at least one address"
        raise ValueError(msg)
    contents = _build_contents(params)
    if not contents:
        msg = "SendGrid: at least one of 'text' or 'html' is required"
        raise ValueError(msg)
    personalization: dict[str, Any] = {
        "to": [{"email": addr} for addr in to_list],
    }
    cc_list = _coerce_addresses(params.get("cc"), field="cc")
    if cc_list:
        personalization["cc"] = [{"email": addr} for addr in cc_list]
    bcc_list = _coerce_addresses(params.get("bcc"), field="bcc")
    if bcc_list:
        personalization["bcc"] = [{"email": addr} for addr in bcc_list]
    sender: dict[str, Any] = {"email": from_email}
    if from_name:
        sender["name"] = from_name
    body: dict[str, Any] = {
        "personalizations": [personalization],
        "from": sender,
        "subject": subject,
        "content": contents,
    }
    reply_to = str(params.get("reply_to") or "").strip()
    if reply_to:
        body["reply_to"] = {"email": reply_to}
    return body


def _build_contents(params: dict[str, Any]) -> list[dict[str, str]]:
    contents: list[dict[str, str]] = []
    text = str(params.get("text") or "").strip()
    if text:
        contents.append({"type": CONTENT_TYPE_TEXT, "value": text})
    html = str(params.get("html") or "").strip()
    if html:
        contents.append({"type": CONTENT_TYPE_HTML, "value": html})
    return contents


def _coerce_addresses(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [addr.strip() for addr in raw.split(",") if addr.strip()]
    if isinstance(raw, list):
        return [str(addr).strip() for addr in raw if str(addr).strip()]
    msg = f"SendGrid: {field!r} must be a string or list of email addresses"
    raise ValueError(msg)


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, str) and msg:
                    return msg
    return f"HTTP {response.status_code}"
