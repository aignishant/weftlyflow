"""Twilio node — Programmable Messaging REST API for SMS/MMS.

Dispatches to ``https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/...``
with HTTP Basic authentication (``account_sid`` + ``auth_token`` from
:class:`~weftlyflow.credentials.types.twilio_api.TwilioApiCredential`).
The Account SID doubles as the Basic-auth username **and** a path
segment, so the node layer reads it from the credential and splices it
into every URL.

Parameters (all expression-capable):

* ``operation`` — ``send_sms``, ``get_message``, ``list_messages``,
  ``delete_message``.
* ``to`` — destination phone number (E.164) for ``send_sms``.
* ``from`` — source phone number (E.164). Required for ``send_sms``
  unless ``messaging_service_sid`` is provided.
* ``messaging_service_sid`` — Messaging Service SID (preferred over
  ``from`` for short codes / copilot flows).
* ``body`` — message text for ``send_sms``.
* ``media_urls`` — optional MMS media URL list.
* ``message_sid`` — for get/delete.
* ``page_size`` — list page size (Twilio caps at 1000).
* ``date_sent`` — ISO-8601 filter for ``list_messages``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``. ``list_messages`` also surfaces a convenience
``messages`` list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote, urlencode

import httpx
import structlog

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    DisplayOptions,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.integrations.twilio.constants import (
    API_BASE_URL,
    API_VERSION_PREFIX,
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE_MESSAGE,
    OP_GET_MESSAGE,
    OP_LIST_MESSAGES,
    OP_SEND_SMS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.twilio.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "twilio_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.twilio_api",)
_MESSAGE_SID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_MESSAGE, OP_DELETE_MESSAGE},
)
_FORM_CONTENT_TYPE: str = "application/x-www-form-urlencoded"

log = structlog.get_logger(__name__)


class TwilioNode(BaseNode):
    """Dispatch a single Twilio Messaging REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.twilio",
        version=1,
        display_name="Twilio",
        description="Send SMS/MMS and manage messages via the Twilio Messaging API.",
        icon="icons/twilio.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "sms"],
        documentation_url="https://www.twilio.com/docs/messaging/api",
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
                default=OP_SEND_SMS,
                required=True,
                options=[
                    PropertyOption(value=OP_SEND_SMS, label="Send SMS"),
                    PropertyOption(value=OP_GET_MESSAGE, label="Get Message"),
                    PropertyOption(value=OP_LIST_MESSAGES, label="List Messages"),
                    PropertyOption(value=OP_DELETE_MESSAGE, label="Delete Message"),
                ],
            ),
            PropertySchema(
                name="to",
                display_name="To",
                type="string",
                placeholder="+15551234567",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_SMS, OP_LIST_MESSAGES]},
                ),
            ),
            PropertySchema(
                name="from",
                display_name="From",
                type="string",
                placeholder="+15557654321",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_SMS, OP_LIST_MESSAGES]},
                ),
            ),
            PropertySchema(
                name="messaging_service_sid",
                display_name="Messaging Service SID",
                type="string",
                description="Alternative to 'from' — use a Messaging Service.",
                display_options=DisplayOptions(show={"operation": [OP_SEND_SMS]}),
            ),
            PropertySchema(
                name="body",
                display_name="Body",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEND_SMS]}),
            ),
            PropertySchema(
                name="media_urls",
                display_name="Media URLs",
                type="json",
                description="List of media URLs for MMS.",
                display_options=DisplayOptions(show={"operation": [OP_SEND_SMS]}),
            ),
            PropertySchema(
                name="message_sid",
                display_name="Message SID",
                type="string",
                placeholder="SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                display_options=DisplayOptions(
                    show={"operation": list(_MESSAGE_SID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="page_size",
                display_name="Page Size",
                type="number",
                default=DEFAULT_LIST_LIMIT,
                display_options=DisplayOptions(show={"operation": [OP_LIST_MESSAGES]}),
            ),
            PropertySchema(
                name="date_sent",
                display_name="Date Sent",
                type="string",
                placeholder="2024-01-15",
                display_options=DisplayOptions(show={"operation": [OP_LIST_MESSAGES]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Twilio Messaging call per input item."""
        sid, token = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        account_prefix = f"{API_VERSION_PREFIX}/Accounts/{quote(sid, safe='')}/"
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            auth=(sid, token),
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        account_prefix=account_prefix,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Twilio: a twilio_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    sid = str(payload.get("account_sid") or "").strip()
    token = str(payload.get("auth_token") or "").strip()
    if not sid or not token:
        msg = "Twilio: credential must have 'account_sid' and 'auth_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return sid, token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    account_prefix: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEND_SMS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Twilio: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, relative_path, form_fields, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    path = account_prefix + relative_path
    content: bytes | None = None
    headers: dict[str, str] = {"Accept": "application/json"}
    if form_fields is not None:
        content = urlencode(form_fields).encode("utf-8")
        headers["Content-Type"] = _FORM_CONTENT_TYPE
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            content=content,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.error("twilio.request_failed", operation=operation, error=str(exc))
        msg = f"Twilio: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_MESSAGES and isinstance(payload, dict):
        messages = payload.get("messages", [])
        result["messages"] = messages if isinstance(messages, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "twilio.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Twilio {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("twilio.ok", operation=operation, status=response.status_code)
    return Item(json=result)


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
            code = payload.get("code")
            return f"{message} (code {code})" if code is not None else message
        more_info = payload.get("more_info")
        if isinstance(more_info, str) and more_info:
            return more_info
    return f"HTTP {status_code}"
