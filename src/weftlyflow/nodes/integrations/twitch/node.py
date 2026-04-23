"""Twitch node — Helix read-only endpoints over the dual-header auth scheme.

Every Helix request carries *both* ``Authorization: Bearer <access_token>``
and ``Client-Id: <client_id>`` headers. The Client-Id is a public
identifier but Twitch rejects the call without it — that pair shape is
the distinctive part of this integration and is enforced node-side from
:class:`~weftlyflow.credentials.types.twitch_api.TwitchApiCredential`.

Parameters (all expression-capable):

* ``operation`` — one of the six read operations.
* ``user_ids`` / ``logins`` — for ``get_users``.
* ``broadcaster_id`` — ``get_channel`` / ``get_followers``.
* ``user_logins`` / ``game_ids`` / ``language`` — stream filters.
* ``video_ids`` / ``user_id`` / ``game_id`` — video filters.
* ``query`` / ``live_only`` — channel search.
* ``first`` / ``after`` — page size and opaque cursor.

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
from weftlyflow.nodes.integrations.twitch.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_GET_CHANNEL,
    OP_GET_FOLLOWERS,
    OP_GET_STREAMS,
    OP_GET_USERS,
    OP_GET_VIDEOS,
    OP_SEARCH_CHANNELS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.twitch.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "twitch_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.twitch_api",)
_BROADCASTER_OPERATIONS: frozenset[str] = frozenset({OP_GET_CHANNEL, OP_GET_FOLLOWERS})
_STREAM_FILTER_OPERATIONS: frozenset[str] = frozenset({OP_GET_STREAMS})
_VIDEO_FILTER_OPERATIONS: frozenset[str] = frozenset({OP_GET_VIDEOS})
_PAGED_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_STREAMS, OP_GET_VIDEOS, OP_GET_FOLLOWERS, OP_SEARCH_CHANNELS},
)

log = structlog.get_logger(__name__)


class TwitchNode(BaseNode):
    """Dispatch a single Twitch Helix call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.twitch",
        version=1,
        display_name="Twitch",
        description="Query Twitch Helix channels, streams, videos, and followers.",
        icon="icons/twitch.svg",
        category=NodeCategory.INTEGRATION,
        group=["media", "streaming"],
        documentation_url="https://dev.twitch.tv/docs/api/reference/",
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
                default=OP_GET_USERS,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_USERS, label="Get Users"),
                    PropertyOption(value=OP_GET_CHANNEL, label="Get Channel"),
                    PropertyOption(value=OP_GET_STREAMS, label="Get Streams"),
                    PropertyOption(value=OP_GET_VIDEOS, label="Get Videos"),
                    PropertyOption(value=OP_GET_FOLLOWERS, label="Get Followers"),
                    PropertyOption(value=OP_SEARCH_CHANNELS, label="Search Channels"),
                ],
            ),
            PropertySchema(
                name="user_ids",
                display_name="User IDs",
                type="string",
                description="Comma-separated user IDs.",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_USERS, OP_GET_STREAMS]},
                ),
            ),
            PropertySchema(
                name="logins",
                display_name="Logins",
                type="string",
                description="Comma-separated Twitch login names.",
                display_options=DisplayOptions(show={"operation": [OP_GET_USERS]}),
            ),
            PropertySchema(
                name="broadcaster_id",
                display_name="Broadcaster ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_BROADCASTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="user_logins",
                display_name="User Logins",
                type="string",
                description="Comma-separated logins to filter streams.",
                display_options=DisplayOptions(
                    show={"operation": list(_STREAM_FILTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="game_ids",
                display_name="Game IDs",
                type="string",
                description="Comma-separated Twitch game IDs.",
                display_options=DisplayOptions(
                    show={"operation": list(_STREAM_FILTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="language",
                display_name="Language",
                type="string",
                description="ISO language code to filter streams.",
                display_options=DisplayOptions(
                    show={"operation": list(_STREAM_FILTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="video_ids",
                display_name="Video IDs",
                type="string",
                description="Comma-separated video IDs.",
                display_options=DisplayOptions(
                    show={"operation": list(_VIDEO_FILTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_VIDEOS, OP_GET_FOLLOWERS]},
                ),
            ),
            PropertySchema(
                name="game_id",
                display_name="Game ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_VIDEO_FILTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="string",
                description="Search string for channel search.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CHANNELS]}),
            ),
            PropertySchema(
                name="live_only",
                display_name="Live Only",
                type="boolean",
                description="Only return currently live channels.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CHANNELS]}),
            ),
            PropertySchema(
                name="first",
                display_name="Page Size",
                type="number",
                description="Number of items per page (max 100).",
                display_options=DisplayOptions(
                    show={"operation": list(_PAGED_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="after",
                display_name="After Cursor",
                type="string",
                description="Opaque cursor from previous page.",
                display_options=DisplayOptions(
                    show={"operation": list(_PAGED_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Twitch Helix call per input item."""
        access_token, client_id = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Client-Id": client_id,
            "Accept": "application/json",
        }
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
                        headers=headers,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Twitch: a twitch_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Twitch: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    client_id = str(payload.get("client_id") or "").strip()
    if not client_id:
        msg = "Twitch: credential has an empty 'client_id'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, client_id


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_GET_USERS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Twitch: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        path, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.get(path, params=query or None, headers=headers)
    except httpx.HTTPError as exc:
        logger.error("twitch.request_failed", operation=operation, error=str(exc))
        msg = f"Twitch: network error on {operation}: {exc}"
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
            "twitch.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Twitch {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("twitch.ok", operation=operation, status=response.status_code)
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
            err = payload.get("error")
            if isinstance(err, str) and err:
                return f"{err}: {message}"
            return message
        err = payload.get("error")
        if isinstance(err, str) and err:
            return err
    return f"HTTP {status_code}"
