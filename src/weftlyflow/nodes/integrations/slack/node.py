"""Slack node — post/update/delete messages and list channels.

This is the first Tier-2 integration (spec §25). The node dispatches to
one of four operations, all of which call Slack's Web API at
``https://slack.com/api/<method>`` with ``Authorization: Bearer <token>``
supplied by a :class:`~weftlyflow.credentials.types.slack_api.SlackApiCredential`.

Parameters (all expression-capable):

* ``operation`` — one of ``post_message``, ``update_message``,
  ``delete_message``, ``list_channels``.
* ``channel``   — channel id (``C0123...``) or name (``#general``). Required
  for message operations; falls back to the credential's
  ``default_channel`` when blank.
* ``text``      — message text (Slack Markdown/mrkdwn).
* ``blocks``    — optional Block Kit payload (list of block dicts).
* ``ts``        — message timestamp; required for update/delete.
* ``thread_ts`` — parent message timestamp to reply in-thread.
* ``as_markdown`` / ``unfurl_links`` — booleans forwarded to Slack.
* ``limit`` / ``cursor`` / ``types`` / ``exclude_archived`` — pagination
  for ``list_channels``.

Credentials:

* slot ``"slack_api"`` — required; accepts either a
  :class:`~weftlyflow.credentials.types.slack_api.SlackApiCredential`
  (raw ``xoxb-``/``xoxp-`` token) or a
  :class:`~weftlyflow.credentials.types.slack_oauth2.SlackOAuth2Credential`
  (OAuth2 flow). Both inject the same ``Authorization: Bearer ...`` header
  and expose ``access_token`` plus an optional ``default_channel``.

Output:

* One item per input item. Each item carries ``operation``, ``ok`` (bool),
  the raw Slack ``response`` dict, and — for ``list_channels`` — a
  convenience ``channels`` list lifted from the response.

Reference: https://api.slack.com/methods.
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
from weftlyflow.nodes.integrations.slack.constants import (
    API_BASE_URL,
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_REACTION,
    OP_DELETE_MESSAGE,
    OP_GET_CHANNEL_HISTORY,
    OP_LIST_CHANNELS,
    OP_LIST_USERS,
    OP_POST_MESSAGE,
    OP_UPDATE_MESSAGE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.slack.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext


_CREDENTIAL_SLOT: str = "slack_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = (
    "weftlyflow.slack_api",
    "weftlyflow.slack_oauth2",
)
_MESSAGE_OPERATIONS: frozenset[str] = frozenset(
    {OP_POST_MESSAGE, OP_UPDATE_MESSAGE, OP_DELETE_MESSAGE},
)
_CHANNEL_REQUIRING_OPERATIONS: frozenset[str] = frozenset(
    _MESSAGE_OPERATIONS | {OP_GET_CHANNEL_HISTORY, OP_ADD_REACTION},
)
_CURSOR_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_CHANNELS, OP_GET_CHANNEL_HISTORY, OP_LIST_USERS},
)
_LIMIT_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_CHANNELS, OP_GET_CHANNEL_HISTORY, OP_LIST_USERS},
)
_COLLECTION_KEY_BY_OPERATION: dict[str, str] = {
    OP_LIST_CHANNELS: "channels",
    OP_GET_CHANNEL_HISTORY: "messages",
    OP_LIST_USERS: "members",
}

log = structlog.get_logger(__name__)


class SlackNode(BaseNode):
    """Dispatch a single Slack Web API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.slack",
        version=1,
        display_name="Slack",
        description="Post, update, or delete Slack messages and list channels.",
        icon="icons/slack.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "chat"],
        documentation_url="https://api.slack.com/methods",
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
                    PropertyOption(value=OP_GET_CHANNEL_HISTORY, label="Get Channel History"),
                    PropertyOption(value=OP_ADD_REACTION, label="Add Reaction"),
                    PropertyOption(value=OP_LIST_USERS, label="List Users"),
                ],
            ),
            PropertySchema(
                name="channel",
                display_name="Channel",
                type="string",
                description="Channel id (C0123...) or name (#general).",
                display_options=DisplayOptions(
                    show={"operation": list(_CHANNEL_REQUIRING_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="text",
                display_name="Text",
                type="string",
                description="Message text. Supports Slack mrkdwn.",
                display_options=DisplayOptions(
                    show={"operation": [OP_POST_MESSAGE, OP_UPDATE_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="blocks",
                display_name="Blocks",
                type="json",
                default=None,
                description="Optional Block Kit payload (list of block objects).",
                display_options=DisplayOptions(
                    show={"operation": [OP_POST_MESSAGE, OP_UPDATE_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="ts",
                display_name="Message Timestamp",
                type="string",
                description="The 'ts' value of the target message.",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_UPDATE_MESSAGE,
                            OP_DELETE_MESSAGE,
                            OP_ADD_REACTION,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="emoji",
                display_name="Emoji",
                type="string",
                description="Emoji name — e.g. 'thumbsup' (no surrounding colons).",
                display_options=DisplayOptions(show={"operation": [OP_ADD_REACTION]}),
            ),
            PropertySchema(
                name="oldest",
                display_name="Oldest",
                type="string",
                description="Return history starting at this Slack ts (exclusive).",
                display_options=DisplayOptions(show={"operation": [OP_GET_CHANNEL_HISTORY]}),
            ),
            PropertySchema(
                name="latest",
                display_name="Latest",
                type="string",
                description="Return history up to this Slack ts (exclusive).",
                display_options=DisplayOptions(show={"operation": [OP_GET_CHANNEL_HISTORY]}),
            ),
            PropertySchema(
                name="inclusive",
                display_name="Inclusive",
                type="boolean",
                default=False,
                description="Include messages at oldest/latest boundaries.",
                display_options=DisplayOptions(show={"operation": [OP_GET_CHANNEL_HISTORY]}),
            ),
            PropertySchema(
                name="include_locale",
                display_name="Include Locale",
                type="boolean",
                default=False,
                display_options=DisplayOptions(show={"operation": [OP_LIST_USERS]}),
            ),
            PropertySchema(
                name="thread_ts",
                display_name="Thread Timestamp",
                type="string",
                description="Reply in-thread by pointing at the parent message ts.",
                display_options=DisplayOptions(show={"operation": [OP_POST_MESSAGE]}),
            ),
            PropertySchema(
                name="as_markdown",
                display_name="Parse as Markdown",
                type="boolean",
                default=True,
                display_options=DisplayOptions(
                    show={"operation": [OP_POST_MESSAGE, OP_UPDATE_MESSAGE]},
                ),
            ),
            PropertySchema(
                name="unfurl_links",
                display_name="Unfurl Links",
                type="boolean",
                default=True,
                display_options=DisplayOptions(show={"operation": [OP_POST_MESSAGE]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                default=DEFAULT_LIST_LIMIT,
                display_options=DisplayOptions(
                    show={"operation": list(_LIMIT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="cursor",
                display_name="Cursor",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CURSOR_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="types",
                display_name="Channel Types",
                type="string",
                default="public_channel",
                description="Comma-separated: public_channel, private_channel, im, mpim.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_CHANNELS]}),
            ),
            PropertySchema(
                name="exclude_archived",
                display_name="Exclude Archived",
                type="boolean",
                default=True,
                display_options=DisplayOptions(show={"operation": [OP_LIST_CHANNELS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Slack API call per input item and emit the response."""
        credential_payload = await self._load_credential(ctx)
        token = str(credential_payload.get("access_token") or "").strip()
        default_channel = str(credential_payload.get("default_channel") or "").strip()
        if not token:
            msg = "Slack: credential has an empty access_token"
            raise NodeExecutionError(msg, node_id=ctx.node.id)

        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await self._dispatch_one(
                        ctx,
                        item,
                        client=client,
                        token=token,
                        default_channel=default_channel,
                        logger=bound,
                    ),
                )
        return [results]

    async def _load_credential(self, ctx: ExecutionContext) -> dict[str, Any]:
        credential = await ctx.load_credential(_CREDENTIAL_SLOT)
        if credential is None:
            msg = "Slack: a Slack API credential is required"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        _, payload = credential
        return payload

    async def _dispatch_one(
        self,
        ctx: ExecutionContext,
        item: Item,
        *,
        client: httpx.AsyncClient,
        token: str,
        default_channel: str,
        logger: Any,
    ) -> Item:
        params = ctx.resolved_params(item=item)
        operation = str(params.get("operation") or OP_POST_MESSAGE).strip()
        if operation not in SUPPORTED_OPERATIONS:
            msg = f"Slack: unsupported operation {operation!r}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)

        try:
            http_method, slack_method, body = build_request(
                operation, params, default_channel=default_channel,
            )
        except ValueError as exc:
            raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
        try:
            response = await client.request(
                http_method,
                f"/{slack_method}",
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
        except httpx.HTTPError as exc:
            logger.error("slack.request_failed", operation=operation, error=str(exc))
            msg = f"Slack: network error calling {slack_method}: {exc}"
            raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc

        payload = _safe_json(response)
        ok = bool(isinstance(payload, dict) and payload.get("ok"))
        result: dict[str, Any] = {
            "operation": operation,
            "ok": ok,
            "response": payload,
        }
        collection_key = _COLLECTION_KEY_BY_OPERATION.get(operation)
        if collection_key is not None and isinstance(payload, dict):
            value = payload.get(collection_key, [])
            result[collection_key] = value if isinstance(value, list) else []
        if not ok:
            error = _error_message(payload, response.status_code)
            logger.warning(
                "slack.api_error",
                operation=operation,
                status=response.status_code,
                error=error,
            )
            msg = f"Slack {slack_method} failed: {error}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        logger.info("slack.ok", operation=operation, status=response.status_code)
        return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, str) and err:
            return err
    return f"HTTP {status_code}"
