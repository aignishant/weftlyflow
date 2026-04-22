"""Pushover node — send push notifications and device glances.

Dispatches to ``https://api.pushover.net/1`` with ``token`` and ``user``
form fields sourced from
:class:`~weftlyflow.credentials.types.pushover_api.PushoverApiCredential`.
Pushover is form-body-authenticated — no ``Authorization`` header is
set on any request.

Parameters (all expression-capable):

* ``operation`` — ``send_notification`` or ``send_glance``.
* ``message`` / ``title`` / ``url`` / ``url_title`` — notification body.
* ``priority`` — integer in [-2, 2]; ``2`` (emergency) requires
  ``retry`` + ``expire``.
* ``sound`` / ``device`` / ``html`` — optional notification modifiers.
* ``text`` / ``subtext`` / ``count`` / ``percent`` — glance fields.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` (or raises ``NodeExecutionError`` when Pushover
reports ``status != 1``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.pushover_api import auth_form_fields
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
from weftlyflow.nodes.integrations.pushover.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_SEND_GLANCE,
    OP_SEND_NOTIFICATION,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.pushover.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "pushover_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.pushover_api",)

log = structlog.get_logger(__name__)


class PushoverNode(BaseNode):
    """Dispatch a single Pushover call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.pushover",
        version=1,
        display_name="Pushover",
        description="Send Pushover push notifications and device glances.",
        icon="icons/pushover.svg",
        category=NodeCategory.INTEGRATION,
        group=["notifications", "messaging"],
        documentation_url="https://pushover.net/api",
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
                default=OP_SEND_NOTIFICATION,
                required=True,
                options=[
                    PropertyOption(
                        value=OP_SEND_NOTIFICATION, label="Send Notification",
                    ),
                    PropertyOption(value=OP_SEND_GLANCE, label="Send Glance"),
                ],
            ),
            PropertySchema(
                name="message",
                display_name="Message",
                type="string",
                description="Notification body (up to 1024 chars).",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION]},
                ),
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION, OP_SEND_GLANCE]},
                ),
            ),
            PropertySchema(
                name="url",
                display_name="URL",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION]},
                ),
            ),
            PropertySchema(
                name="url_title",
                display_name="URL Title",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION]},
                ),
            ),
            PropertySchema(
                name="priority",
                display_name="Priority",
                type="number",
                description="Integer in [-2, 2]; 2 requires retry + expire.",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION]},
                ),
            ),
            PropertySchema(
                name="retry",
                display_name="Retry (seconds)",
                type="number",
                description="Resend interval for emergency priority (>= 30).",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION]},
                ),
            ),
            PropertySchema(
                name="expire",
                display_name="Expire (seconds)",
                type="number",
                description="Total retry duration for emergency priority.",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION]},
                ),
            ),
            PropertySchema(
                name="sound",
                display_name="Sound",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION]},
                ),
            ),
            PropertySchema(
                name="device",
                display_name="Device",
                type="string",
                description="Target device name (empty = all devices).",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION, OP_SEND_GLANCE]},
                ),
            ),
            PropertySchema(
                name="html",
                display_name="HTML",
                type="boolean",
                description="Render message as limited HTML.",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_NOTIFICATION]},
                ),
            ),
            PropertySchema(
                name="text",
                display_name="Text",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEND_GLANCE]}),
            ),
            PropertySchema(
                name="subtext",
                display_name="Subtext",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEND_GLANCE]}),
            ),
            PropertySchema(
                name="count",
                display_name="Count",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_SEND_GLANCE]}),
            ),
            PropertySchema(
                name="percent",
                display_name="Percent",
                type="number",
                description="Integer in [0, 100].",
                display_options=DisplayOptions(show={"operation": [OP_SEND_GLANCE]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Pushover call per input item."""
        auth_fields = await _resolve_credential(ctx)
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
                        auth_fields=auth_fields,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credential(ctx: ExecutionContext) -> dict[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Pushover: a pushover_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    fields = auth_form_fields(payload)
    if not fields["token"]:
        msg = "Pushover: credential has an empty 'app_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not fields["user"]:
        msg = "Pushover: credential has an empty 'user_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return fields


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    auth_fields: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEND_NOTIFICATION).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Pushover: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        path, form = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    body = {**auth_fields, **form}
    try:
        response = await client.post(path, data=body)
    except httpx.HTTPError as exc:
        logger.error("pushover.request_failed", operation=operation, error=str(exc))
        msg = f"Pushover: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "pushover.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Pushover {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if isinstance(payload, dict) and payload.get("status") != 1:
        error = _error_message(payload, response.status_code)
        logger.warning("pushover.status_error", operation=operation, error=error)
        msg = f"Pushover {operation} failed: {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("pushover.ok", operation=operation, status=response.status_code)
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
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            return ", ".join(str(entry) for entry in errors)
        if isinstance(errors, str) and errors:
            return errors
        message = payload.get("errors_as_string") or payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
