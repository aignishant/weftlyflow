"""Discord node — send/edit/delete channel messages, fetch channel metadata.

Dispatches to Discord's REST API at ``https://discord.com/api/v10``. Every
request carries ``Authorization: Bot <token>`` from a
:class:`~weftlyflow.credentials.types.discord_bot.DiscordBotCredential`.

Parameters (all expression-capable):

* ``operation`` — ``send_message``, ``get_channel``, ``edit_message``,
  ``delete_message``.
* ``channel_id`` — required for every operation.
* ``message_id`` — required for ``edit_message`` and ``delete_message``.
* ``content`` — plain-text message body (up to 2000 chars).
* ``embeds`` — optional list of Discord embed objects.
* ``tts`` — boolean, optional text-to-speech flag.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` object. ``delete_message`` returns an empty response
object because the API replies with 204 No Content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

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
from weftlyflow.nodes.integrations.discord.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE_MESSAGE,
    OP_EDIT_MESSAGE,
    OP_GET_CHANNEL,
    OP_SEND_MESSAGE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.discord.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "discord_bot"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.discord_bot",)
_MESSAGE_OPERATIONS: frozenset[str] = frozenset(
    {OP_SEND_MESSAGE, OP_EDIT_MESSAGE, OP_DELETE_MESSAGE},
)

log = structlog.get_logger(__name__)


class DiscordNode(BaseNode):
    """Dispatch a single Discord REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.discord",
        version=1,
        display_name="Discord",
        description="Send, edit, or delete Discord channel messages and read channel metadata.",
        icon="icons/discord.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "chat"],
        documentation_url="https://discord.com/developers/docs/reference",
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
                default=OP_SEND_MESSAGE,
                required=True,
                options=[
                    PropertyOption(value=OP_SEND_MESSAGE, label="Send Message"),
                    PropertyOption(value=OP_GET_CHANNEL, label="Get Channel"),
                    PropertyOption(value=OP_EDIT_MESSAGE, label="Edit Message"),
                    PropertyOption(value=OP_DELETE_MESSAGE, label="Delete Message"),
                ],
            ),
            PropertySchema(
                name="channel_id",
                display_name="Channel ID",
                type="string",
                required=True,
            ),
            PropertySchema(
                name="message_id",
                display_name="Message ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_EDIT_MESSAGE, OP_DELETE_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="content",
                display_name="Content",
                type="string",
                description="Plain-text message body (up to 2000 characters).",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_MESSAGE, OP_EDIT_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="embeds",
                display_name="Embeds",
                type="json",
                description="List of Discord embed objects.",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_MESSAGE, OP_EDIT_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="tts",
                display_name="Text-to-Speech",
                type="boolean",
                default=False,
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_MESSAGE, OP_EDIT_MESSAGE]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Discord REST call per input item."""
        token = await _resolve_token(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(ctx, item, client=client, token=token, logger=bound),
                )
        return [results]


async def _resolve_token(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Discord: a Discord bot credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("bot_token") or "").strip()
    if not token:
        msg = "Discord: credential has an empty 'bot_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SEND_MESSAGE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Discord: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.request(
            method,
            path,
            json=body,
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("discord.request_failed", operation=operation, error=str(exc))
        msg = f"Discord: network error on {operation}: {exc}"
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
            "discord.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Discord {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("discord.ok", operation=operation, status=response.status_code)
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
            return message
    return f"HTTP {status_code}"
