"""Rocket.Chat node — messaging, channels, users via REST v1.

Dispatches to a credential-owned ``base_url`` (self-hosted Rocket.Chat
servers) with the distinctive ``X-Auth-Token`` + ``X-User-Id``
dual-header auth pair. Both headers are mandatory; omitting either
returns 401. Auth is handled by
:class:`~weftlyflow.credentials.types.rocket_chat_api.RocketChatApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``post_message``, ``update_message``,
  ``delete_message``, ``list_channels``, ``create_channel``,
  ``get_user``.
* ``room_id`` — target room/channel id.
* ``text`` — message body.
* ``message_id`` — for update/delete.
* ``name`` — new channel name.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
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
from weftlyflow.nodes.integrations.rocket_chat.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_CHANNEL,
    OP_DELETE_MESSAGE,
    OP_GET_USER,
    OP_LIST_CHANNELS,
    OP_POST_MESSAGE,
    OP_UPDATE_MESSAGE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.rocket_chat.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "rocket_chat_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.rocket_chat_api",)
_MESSAGE_OPERATIONS: frozenset[str] = frozenset(
    {OP_POST_MESSAGE, OP_UPDATE_MESSAGE, OP_DELETE_MESSAGE},
)

log = structlog.get_logger(__name__)


class RocketChatNode(BaseNode):
    """Dispatch a single Rocket.Chat REST v1 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.rocket_chat",
        version=1,
        display_name="Rocket.Chat",
        description="Post, update, delete messages; list/create channels on Rocket.Chat.",
        icon="icons/rocket_chat.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "chat"],
        documentation_url="https://developer.rocket.chat/reference/api/rest-api",
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
                default=OP_POST_MESSAGE,
                required=True,
                options=[
                    PropertyOption(value=OP_POST_MESSAGE, label="Post Message"),
                    PropertyOption(value=OP_UPDATE_MESSAGE, label="Update Message"),
                    PropertyOption(value=OP_DELETE_MESSAGE, label="Delete Message"),
                    PropertyOption(value=OP_LIST_CHANNELS, label="List Channels"),
                    PropertyOption(value=OP_CREATE_CHANNEL, label="Create Channel"),
                    PropertyOption(value=OP_GET_USER, label="Get User"),
                ],
            ),
            PropertySchema(
                name="room_id",
                display_name="Room ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_MESSAGE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="text",
                display_name="Text",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_POST_MESSAGE, OP_UPDATE_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="message_id",
                display_name="Message ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPDATE_MESSAGE, OP_DELETE_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="alias",
                display_name="Alias",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_POST_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="emoji",
                display_name="Emoji",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_POST_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="attachments",
                display_name="Attachments",
                type="json",
                display_options=DisplayOptions(
                    show={"operation": [OP_POST_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="name",
                display_name="Channel Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_CHANNEL]},
                ),
            ),
            PropertySchema(
                name="members",
                display_name="Members",
                type="json",
                description="Array of usernames to invite on creation.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_CHANNEL]},
                ),
            ),
            PropertySchema(
                name="read_only",
                display_name="Read Only",
                type="boolean",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_CHANNEL]},
                ),
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_USER]},
                ),
            ),
            PropertySchema(
                name="username",
                display_name="Username",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_USER]},
                ),
            ),
            PropertySchema(
                name="count",
                display_name="Count",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHANNELS]},
                ),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHANNELS]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Rocket.Chat REST v1 call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            msg = "Rocket.Chat: credential has an empty 'base_url'"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        injector=injector,
                        creds=payload,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Rocket.Chat: a rocket_chat_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("auth_token") or "").strip():
        msg = "Rocket.Chat: credential has an empty 'auth_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not str(payload.get("user_id") or "").strip():
        msg = "Rocket.Chat: credential has an empty 'user_id'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_POST_MESSAGE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Rocket.Chat: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = client.build_request(
        method,
        path,
        params=query or None,
        json=body,
        headers=request_headers,
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("rocket_chat.request_failed", operation=operation, error=str(exc))
        msg = f"Rocket.Chat: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    ok_envelope = isinstance(payload, dict) and payload.get("success") is False
    if response.status_code >= httpx.codes.BAD_REQUEST or ok_envelope:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "rocket_chat.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Rocket.Chat {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("rocket_chat.ok", operation=operation, status=response.status_code)
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
        for key in ("error", "message", "errorType"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
