"""Mattermost node — v4 REST API for self-hosted chat servers.

Dispatches to ``<credential base_url>/api/v4/...`` with
``Authorization: Bearer <access_token>`` sourced from
:class:`~weftlyflow.credentials.types.mattermost_api.MattermostApiCredential`.
The base URL is part of the credential (Mattermost is self-hosted, so
every tenant lives at its own host) and is normalized via
:func:`weftlyflow.credentials.types.mattermost_api.base_url_from`.

Parameters (all expression-capable):

* ``operation`` — ``post_message``, ``update_post``, ``delete_post``,
  ``get_channel``, ``list_channels_for_user``, ``get_user_by_username``.
* ``channel_id`` — target channel for posting or fetching.
* ``message`` / ``root_id`` / ``props`` / ``file_ids`` —
  ``post_message``.
* ``post_id`` — target post for update/delete.
* ``fields`` — JSON patch body for ``update_post``.
* ``user_id`` / ``team_id`` — ``list_channels_for_user``
  (``user_id`` defaults to ``me``).
* ``username`` — ``get_user_by_username``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.mattermost_api import base_url_from
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
from weftlyflow.nodes.integrations.mattermost.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE_POST,
    OP_GET_CHANNEL,
    OP_GET_USER_BY_USERNAME,
    OP_LIST_CHANNELS_FOR_USER,
    OP_POST_MESSAGE,
    OP_UPDATE_POST,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.mattermost.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "mattermost_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.mattermost_api",)
_CHANNEL_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_POST_MESSAGE, OP_GET_CHANNEL},
)
_POST_ID_OPERATIONS: frozenset[str] = frozenset({OP_UPDATE_POST, OP_DELETE_POST})

log = structlog.get_logger(__name__)


class MattermostNode(BaseNode):
    """Dispatch a single Mattermost v4 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.mattermost",
        version=1,
        display_name="Mattermost",
        description="Post and manage Mattermost messages, channels, and users.",
        icon="icons/mattermost.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "chat"],
        documentation_url="https://api.mattermost.com/",
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
                    PropertyOption(value=OP_UPDATE_POST, label="Update Post"),
                    PropertyOption(value=OP_DELETE_POST, label="Delete Post"),
                    PropertyOption(value=OP_GET_CHANNEL, label="Get Channel"),
                    PropertyOption(
                        value=OP_LIST_CHANNELS_FOR_USER,
                        label="List Channels for User",
                    ),
                    PropertyOption(
                        value=OP_GET_USER_BY_USERNAME, label="Get User by Username",
                    ),
                ],
            ),
            PropertySchema(
                name="channel_id",
                display_name="Channel ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CHANNEL_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="message",
                display_name="Message",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_POST_MESSAGE]}),
            ),
            PropertySchema(
                name="root_id",
                display_name="Root Post ID",
                type="string",
                description="Post ID to thread this reply under.",
                display_options=DisplayOptions(show={"operation": [OP_POST_MESSAGE]}),
            ),
            PropertySchema(
                name="props",
                display_name="Props",
                type="json",
                description="Arbitrary metadata object attached to the post.",
                display_options=DisplayOptions(show={"operation": [OP_POST_MESSAGE]}),
            ),
            PropertySchema(
                name="file_ids",
                display_name="File IDs",
                type="string",
                description="Comma-separated IDs of pre-uploaded files.",
                display_options=DisplayOptions(show={"operation": [OP_POST_MESSAGE]}),
            ),
            PropertySchema(
                name="post_id",
                display_name="Post ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_POST_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="JSON patch body for update_post.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_POST]}),
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                description="Defaults to 'me' when blank.",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHANNELS_FOR_USER]},
                ),
            ),
            PropertySchema(
                name="team_id",
                display_name="Team ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHANNELS_FOR_USER]},
                ),
            ),
            PropertySchema(
                name="username",
                display_name="Username",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_USER_BY_USERNAME]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Mattermost REST call per input item."""
        token, base_url = await _resolve_credentials(ctx)
        try:
            normalized_base = base_url_from(base_url)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=normalized_base, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, token=token, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Mattermost: a mattermost_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Mattermost: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    base_url = str(payload.get("base_url") or "").strip()
    if not base_url:
        msg = "Mattermost: credential has an empty 'base_url'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, base_url


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_POST_MESSAGE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Mattermost: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("mattermost.request_failed", operation=operation, error=str(exc))
        msg = f"Mattermost: network error on {operation}: {exc}"
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
            "mattermost.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Mattermost {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("mattermost.ok", operation=operation, status=response.status_code)
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
            detailed = payload.get("detailed_error")
            if isinstance(detailed, str) and detailed:
                return f"{message}: {detailed}"
            return message
        detailed = payload.get("detailed_error")
        if isinstance(detailed, str) and detailed:
            return detailed
    return f"HTTP {status_code}"
