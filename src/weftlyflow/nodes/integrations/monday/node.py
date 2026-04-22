"""Monday.com node — GraphQL v2 dispatch for boards, items, and updates.

Every operation posts a ``{"query": ..., "variables": ...}`` body to the
single Monday.com GraphQL endpoint. The credential supplies a raw
``Authorization`` header (no ``Bearer`` prefix) via
:class:`~weftlyflow.credentials.types.monday_api.MondayApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``get_boards``, ``get_board``, ``get_items``,
  ``create_item``, ``change_column_values``, ``create_update``.
* ``board_id`` — target board (all ops except ``get_boards``,
  ``create_update``).
* ``item_id`` — target item (``change_column_values``, ``create_update``).
* ``item_name`` — new-item display name (``create_item``).
* ``group_id`` — optional group placement for ``create_item``.
* ``column_values`` — JSON object of column updates (create/change ops).
* ``body`` — update text for ``create_update``.
* ``limit`` — page size for listing ops (capped at 500).

Output: one item per input item with ``operation``, ``status``, and the
parsed GraphQL ``response`` (``data`` / ``errors``).
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
from weftlyflow.nodes.integrations.monday.constants import (
    API_URL,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CHANGE_COLUMN_VALUES,
    OP_CREATE_ITEM,
    OP_CREATE_UPDATE,
    OP_GET_BOARD,
    OP_GET_BOARDS,
    OP_GET_ITEMS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.monday.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "monday_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.monday_api",)
_BOARD_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_BOARD, OP_GET_ITEMS, OP_CREATE_ITEM, OP_CHANGE_COLUMN_VALUES},
)
_ITEM_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_CHANGE_COLUMN_VALUES, OP_CREATE_UPDATE},
)
_LIMIT_OPERATIONS: frozenset[str] = frozenset({OP_GET_BOARDS, OP_GET_ITEMS})
_COLUMN_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_ITEM, OP_CHANGE_COLUMN_VALUES},
)

log = structlog.get_logger(__name__)


class MondayNode(BaseNode):
    """Dispatch a single Monday.com GraphQL call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.monday",
        version=1,
        display_name="Monday.com",
        description="Query and mutate Monday.com boards via GraphQL.",
        icon="icons/monday.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "project-management"],
        documentation_url="https://developer.monday.com/api-reference/docs",
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
                default=OP_GET_BOARDS,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_BOARDS, label="Get Boards"),
                    PropertyOption(value=OP_GET_BOARD, label="Get Board"),
                    PropertyOption(value=OP_GET_ITEMS, label="Get Items"),
                    PropertyOption(value=OP_CREATE_ITEM, label="Create Item"),
                    PropertyOption(
                        value=OP_CHANGE_COLUMN_VALUES, label="Change Column Values",
                    ),
                    PropertyOption(value=OP_CREATE_UPDATE, label="Create Update"),
                ],
            ),
            PropertySchema(
                name="board_id",
                display_name="Board ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_BOARD_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="item_id",
                display_name="Item ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_ITEM_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="item_name",
                display_name="Item Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ITEM]}),
            ),
            PropertySchema(
                name="group_id",
                display_name="Group ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ITEM]}),
            ),
            PropertySchema(
                name="column_values",
                display_name="Column Values",
                type="json",
                description="JSON object keyed by column ID.",
                display_options=DisplayOptions(
                    show={"operation": list(_COLUMN_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="body",
                display_name="Update Body",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_UPDATE]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                default=DEFAULT_PAGE_LIMIT,
                display_options=DisplayOptions(
                    show={"operation": list(_LIMIT_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Monday.com GraphQL call per input item."""
        token = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, token=token, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Monday: a monday_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("api_token") or "").strip()
    if not token:
        msg = "Monday: credential has an empty 'api_token'"
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
    operation = str(params.get("operation") or OP_GET_BOARDS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Monday: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        query, variables = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.post(
            API_URL,
            json={"query": query, "variables": variables},
            headers={
                "Authorization": token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("monday.request_failed", operation=operation, error=str(exc))
        msg = f"Monday: network error on {operation}: {exc}"
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
            "monday.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Monday {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if isinstance(payload, dict) and payload.get("errors"):
        error = _error_message(payload, response.status_code)
        logger.warning(
            "monday.graphql_error", operation=operation, error=error,
        )
        msg = f"Monday {operation} returned errors: {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("monday.ok", operation=operation, status=response.status_code)
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
            parts: list[str] = []
            for err in errors:
                if isinstance(err, dict):
                    message = err.get("message")
                    if message:
                        parts.append(str(message))
                elif isinstance(err, str):
                    parts.append(err)
            if parts:
                return "; ".join(parts)
        message = payload.get("error_message") or payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
