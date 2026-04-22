"""Mailgun node — send a transactional email via the v3 Messages API.

POSTs one email per input item to
``https://api[.eu].mailgun.net/v3/{domain}/messages`` with an
``application/x-www-form-urlencoded`` body. Authentication is HTTP Basic
with username ``api`` and the Mailgun API key as password — handled by a
:class:`~weftlyflow.credentials.types.basic_auth.BasicAuthCredential` row.

Parameters (all expression-capable):

* ``operation`` — currently only ``send_email``.
* ``domain`` — sending domain registered with Mailgun.
* ``region`` — ``us`` (default) or ``eu`` — selects the API host.
* ``from_address`` — full "Name <addr@domain>" or bare address.
* ``to`` — comma-separated recipient addresses (repeats ``to`` fields).
* ``cc`` / ``bcc`` — optional recipient lists.
* ``subject`` — message subject.
* ``text`` / ``html`` — message body. At least one is required.
* ``tags`` — comma-separated list forwarded as repeated ``o:tag`` fields.
* ``tracking`` — boolean mapped to ``o:tracking`` (``yes`` / ``no``).

Output: one item per input item with ``operation``, ``status``, ``id``
(the ``id`` field Mailgun returns on success), and the parsed
``response`` body.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlencode

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
from weftlyflow.nodes.integrations.mailgun.constants import (
    API_BASE_URL_EU,
    API_BASE_URL_US,
    DEFAULT_TIMEOUT_SECONDS,
    OP_SEND_EMAIL,
    REGION_EU,
    REGION_US,
    SUPPORTED_OPERATIONS,
    VALID_REGIONS,
)

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "mailgun_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.basic_auth",)

log = structlog.get_logger(__name__)


class MailgunNode(BaseNode):
    """Send a transactional email per input item via Mailgun."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.mailgun",
        version=1,
        display_name="Mailgun",
        description="Send transactional email via Mailgun's v3 Messages API.",
        icon="icons/mailgun.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "email"],
        documentation_url="https://documentation.mailgun.com/en/latest/api-sending.html",
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
                name="domain",
                display_name="Sending Domain",
                type="string",
                required=True,
                placeholder="mg.example.com",
            ),
            PropertySchema(
                name="region",
                display_name="Region",
                type="options",
                default=REGION_US,
                options=[
                    PropertyOption(value=REGION_US, label="US"),
                    PropertyOption(value=REGION_EU, label="EU"),
                ],
            ),
            PropertySchema(
                name="from_address",
                display_name="From",
                type="string",
                required=True,
                description="Full 'Name <addr@domain>' or bare email.",
            ),
            PropertySchema(
                name="to",
                display_name="To",
                type="string",
                required=True,
                description="Comma-separated recipient addresses.",
            ),
            PropertySchema(name="cc", display_name="Cc", type="string"),
            PropertySchema(name="bcc", display_name="Bcc", type="string"),
            PropertySchema(
                name="subject",
                display_name="Subject",
                type="string",
                required=True,
            ),
            PropertySchema(name="text", display_name="Plain Text Body", type="string"),
            PropertySchema(name="html", display_name="HTML Body", type="string"),
            PropertySchema(
                name="tags",
                display_name="Tags",
                type="string",
                description="Comma-separated tags forwarded as 'o:tag' fields.",
            ),
            PropertySchema(
                name="tracking",
                display_name="Tracking",
                type="boolean",
                default=True,
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Mailgun send per input item."""
        username, password = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = [
            await _dispatch_one(
                ctx,
                item,
                username=username,
                password=password,
                logger=bound,
            )
            for item in seed
        ]
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Mailgun: a basic-auth credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not username or not password:
        msg = "Mailgun: credential must have both 'username' and 'password'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return username, password


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    username: str,
    password: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEND_EMAIL).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Mailgun: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        base_url, path, fields = _build_send_email(params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    body = urlencode(fields).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            auth=(username, password),
        ) as client:
            response = await client.post(path, content=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.error("mailgun.request_failed", error=str(exc))
        msg = f"Mailgun: network error sending email: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    message_id = ""
    if isinstance(payload, dict):
        raw_id = payload.get("id")
        if isinstance(raw_id, str):
            message_id = raw_id
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "id": message_id,
        "response": payload,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning("mailgun.api_error", status=response.status_code, error=error)
        msg = f"Mailgun send_email failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("mailgun.ok", status=response.status_code)
    return Item(json=result)


def _build_send_email(params: dict[str, Any]) -> tuple[str, str, list[tuple[str, str]]]:
    domain = str(params.get("domain") or "").strip()
    if not domain:
        msg = "Mailgun: 'domain' is required"
        raise ValueError(msg)
    region = str(params.get("region") or REGION_US).strip().lower() or REGION_US
    if region not in VALID_REGIONS:
        msg = f"Mailgun: invalid region {region!r} — must be one of {sorted(VALID_REGIONS)}"
        raise ValueError(msg)
    base_url = API_BASE_URL_EU if region == REGION_EU else API_BASE_URL_US
    from_address = str(params.get("from_address") or "").strip()
    if not from_address:
        msg = "Mailgun: 'from_address' is required"
        raise ValueError(msg)
    subject = str(params.get("subject") or "").strip()
    if not subject:
        msg = "Mailgun: 'subject' is required"
        raise ValueError(msg)
    to_list = _coerce_addresses(params.get("to"), field="to")
    if not to_list:
        msg = "Mailgun: 'to' must contain at least one address"
        raise ValueError(msg)
    text = str(params.get("text") or "")
    html = str(params.get("html") or "")
    if not text.strip() and not html.strip():
        msg = "Mailgun: at least one of 'text' or 'html' is required"
        raise ValueError(msg)
    fields: list[tuple[str, str]] = [
        ("from", from_address),
        ("subject", subject),
    ]
    fields.extend(("to", addr) for addr in to_list)
    for addr in _coerce_addresses(params.get("cc"), field="cc"):
        fields.append(("cc", addr))
    for addr in _coerce_addresses(params.get("bcc"), field="bcc"):
        fields.append(("bcc", addr))
    if text.strip():
        fields.append(("text", text))
    if html.strip():
        fields.append(("html", html))
    tags = _coerce_string_list(params.get("tags"), field="tags")
    fields.extend(("o:tag", tag) for tag in tags)
    tracking = params.get("tracking")
    if isinstance(tracking, bool):
        fields.append(("o:tracking", "yes" if tracking else "no"))
    path = f"/v3/{domain}/messages"
    return base_url, path, fields


def _coerce_addresses(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [addr.strip() for addr in raw.split(",") if addr.strip()]
    if isinstance(raw, list):
        return [str(addr).strip() for addr in raw if str(addr).strip()]
    msg = f"Mailgun: {field!r} must be a string or list of email addresses"
    raise ValueError(msg)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Mailgun: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
