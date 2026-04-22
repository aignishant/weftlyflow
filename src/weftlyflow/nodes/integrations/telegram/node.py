"""Telegram node — send/edit/delete messages via the Bot API.

Dispatches to ``https://api.telegram.org/bot<TOKEN>/<method>`` with a
JSON body. Unlike most HTTP APIs, Telegram embeds the bot token in the
URL path rather than the ``Authorization`` header — so the credential
type's ``inject()`` is a no-op and this node composes the URL itself
from the resolved ``bot_token``.

Parameters (all expression-capable):

* ``operation`` — ``send_message``, ``send_photo``, ``edit_message_text``,
  ``delete_message``, ``get_updates``.
* ``chat_id`` — integer or ``@channel`` handle; required for all
  operations except ``get_updates``.
* ``text`` — for ``send_message`` / ``edit_message_text``
  (≤4096 chars).
* ``photo`` / ``caption`` — for ``send_photo``.
* ``message_id`` — for edit/delete.
* ``parse_mode`` — ``Markdown`` / ``MarkdownV2`` / ``HTML``.
* ``disable_notification`` / ``disable_web_page_preview`` — booleans.
* ``reply_to_message_id`` — positive integer.
* ``offset`` / ``limit`` / ``long_poll_timeout`` — for ``get_updates``.

Output: one item per input item with ``operation``, ``status``, ``ok``
(the Telegram envelope flag), and the parsed ``response.result``.
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
from weftlyflow.nodes.integrations.telegram.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE_MESSAGE,
    OP_EDIT_MESSAGE_TEXT,
    OP_GET_UPDATES,
    OP_SEND_MESSAGE,
    OP_SEND_PHOTO,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.telegram.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "telegram_bot"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.telegram_bot",)
_MESSAGE_OPERATIONS: frozenset[str] = frozenset(
    {OP_SEND_MESSAGE, OP_SEND_PHOTO, OP_EDIT_MESSAGE_TEXT, OP_DELETE_MESSAGE},
)
_PARSE_MODE_OPERATIONS: frozenset[str] = frozenset(
    {OP_SEND_MESSAGE, OP_SEND_PHOTO, OP_EDIT_MESSAGE_TEXT},
)

log = structlog.get_logger(__name__)


class TelegramNode(BaseNode):
    """Dispatch a single Telegram Bot API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.telegram",
        version=1,
        display_name="Telegram",
        description="Send and manage messages via the Telegram Bot API.",
        icon="icons/telegram.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "chat"],
        documentation_url="https://core.telegram.org/bots/api",
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
                    PropertyOption(value=OP_SEND_PHOTO, label="Send Photo"),
                    PropertyOption(value=OP_EDIT_MESSAGE_TEXT, label="Edit Message Text"),
                    PropertyOption(value=OP_DELETE_MESSAGE, label="Delete Message"),
                    PropertyOption(value=OP_GET_UPDATES, label="Get Updates"),
                ],
            ),
            PropertySchema(
                name="chat_id",
                display_name="Chat ID",
                type="string",
                description="Numeric chat id or '@channelusername'.",
                display_options=DisplayOptions(
                    show={"operation": list(_MESSAGE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="text",
                display_name="Text",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_MESSAGE, OP_EDIT_MESSAGE_TEXT]},
                ),
            ),
            PropertySchema(
                name="photo",
                display_name="Photo",
                type="string",
                description="Photo URL or pre-uploaded file_id.",
                display_options=DisplayOptions(show={"operation": [OP_SEND_PHOTO]}),
            ),
            PropertySchema(
                name="caption",
                display_name="Caption",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEND_PHOTO]}),
            ),
            PropertySchema(
                name="message_id",
                display_name="Message ID",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_EDIT_MESSAGE_TEXT, OP_DELETE_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="parse_mode",
                display_name="Parse Mode",
                type="options",
                default="",
                options=[
                    PropertyOption(value="", label="Plain"),
                    PropertyOption(value="Markdown", label="Markdown"),
                    PropertyOption(value="MarkdownV2", label="MarkdownV2"),
                    PropertyOption(value="HTML", label="HTML"),
                ],
                display_options=DisplayOptions(
                    show={"operation": list(_PARSE_MODE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="disable_notification",
                display_name="Silent",
                type="boolean",
                default=False,
                display_options=DisplayOptions(
                    show={"operation": [OP_SEND_MESSAGE, OP_SEND_PHOTO]},
                ),
            ),
            PropertySchema(
                name="disable_web_page_preview",
                display_name="Disable Link Preview",
                type="boolean",
                default=False,
                display_options=DisplayOptions(show={"operation": [OP_SEND_MESSAGE]}),
            ),
            PropertySchema(
                name="reply_to_message_id",
                display_name="Reply To",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_SEND_MESSAGE]}),
            ),
            PropertySchema(
                name="offset",
                display_name="Update Offset",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_GET_UPDATES]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_GET_UPDATES]}),
            ),
            PropertySchema(
                name="long_poll_timeout",
                display_name="Long-Poll Timeout (s)",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_GET_UPDATES]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Bot API call per input item."""
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
        msg = "Telegram: a telegram_bot credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("bot_token") or "").strip()
    if not token:
        msg = "Telegram: credential has an empty 'bot_token'"
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
        msg = f"Telegram: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method_name, body = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    path = f"/bot{token}/{method_name}"
    try:
        response = await client.post(path, json=body)
    except httpx.HTTPError as exc:
        logger.error("telegram.request_failed", operation=operation, error=str(exc))
        msg = f"Telegram: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    ok = bool(payload.get("ok")) if isinstance(payload, dict) else False
    telegram_result: Any = payload.get("result") if isinstance(payload, dict) else None
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "ok": ok,
        "response": telegram_result if telegram_result is not None else payload,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST or not ok:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "telegram.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Telegram {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("telegram.ok", operation=operation, status=response.status_code)
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
        description = payload.get("description")
        if isinstance(description, str) and description:
            return description
    return f"HTTP {status_code}"
