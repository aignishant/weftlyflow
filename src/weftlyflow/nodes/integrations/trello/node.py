"""Trello node — board/card CRUD via the Trello v1 REST API.

Authenticates by appending ``key=<api_key>&token=<api_token>`` to every
outbound URL (handled by the credential type's ``inject()``). All
operation parameters — ``name``, ``desc``, label lists, etc. — are sent
as *query-string* values; Trello accepts no request body.

Parameters (all expression-capable):

* ``operation`` — ``get_board``, ``list_cards``, ``get_card``,
  ``create_card``, ``update_card``, ``delete_card``.
* ``board_id`` — for ``get_board`` / ``list_cards``.
* ``card_id`` — for ``get_card`` / ``update_card`` / ``delete_card``.
* ``list_id`` / ``name`` — for ``create_card``.
* ``extra_fields`` — optional JSON of additional create-card fields
  (``desc``, ``due``, ``pos``, ``idMembers``, ``idLabels``,
  ``urlSource``).
* ``fields`` — JSON of updates for ``update_card`` (``name``, ``desc``,
  ``closed``, ``idList``, ``idBoard``, ``due``, ``dueComplete``,
  ``pos``).
* ``filter`` — ``list_cards`` filter (``all``, ``open``, ``closed``,
  ``visible``).

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` object. For ``list_cards`` a convenience ``cards``
list is also surfaced.
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
from weftlyflow.nodes.integrations.trello.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_CARD,
    OP_DELETE_CARD,
    OP_GET_BOARD,
    OP_GET_CARD,
    OP_LIST_CARDS,
    OP_UPDATE_CARD,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.trello.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "trello_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.trello_api",)
_BOARD_OPERATIONS: frozenset[str] = frozenset({OP_GET_BOARD, OP_LIST_CARDS})
_CARD_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_CARD, OP_UPDATE_CARD, OP_DELETE_CARD},
)

log = structlog.get_logger(__name__)


class TrelloNode(BaseNode):
    """Dispatch a single Trello REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.trello",
        version=1,
        display_name="Trello",
        description="Create, update, and retrieve Trello boards and cards.",
        icon="icons/trello.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "project-management"],
        documentation_url="https://developer.atlassian.com/cloud/trello/rest/",
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
                default=OP_LIST_CARDS,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_BOARD, label="Get Board"),
                    PropertyOption(value=OP_LIST_CARDS, label="List Cards on Board"),
                    PropertyOption(value=OP_GET_CARD, label="Get Card"),
                    PropertyOption(value=OP_CREATE_CARD, label="Create Card"),
                    PropertyOption(value=OP_UPDATE_CARD, label="Update Card"),
                    PropertyOption(value=OP_DELETE_CARD, label="Delete Card"),
                ],
            ),
            PropertySchema(
                name="board_id",
                display_name="Board ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_BOARD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="card_id",
                display_name="Card ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CARD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="list_id",
                display_name="List ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CARD]}),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CARD]}),
            ),
            PropertySchema(
                name="extra_fields",
                display_name="Extra Fields",
                type="json",
                description=(
                    "Optional: {desc, due, pos, idMembers, idLabels, urlSource}."
                ),
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CARD]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="Object of fields to update on the card.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_CARD]}),
            ),
            PropertySchema(
                name="filter",
                display_name="Filter",
                type="options",
                default="open",
                options=[
                    PropertyOption(value="all", label="All"),
                    PropertyOption(value="open", label="Open"),
                    PropertyOption(value="closed", label="Closed"),
                    PropertyOption(value="visible", label="Visible"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_LIST_CARDS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Trello REST call per input item."""
        api_key, api_token = await _resolve_key_and_token(ctx)
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
                        api_key=api_key,
                        api_token=api_token,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_key_and_token(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Trello: a trello_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    api_token = str(payload.get("api_token") or "").strip()
    if not api_key or not api_token:
        msg = "Trello: credential must have both 'api_key' and 'api_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return api_key, api_token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    api_token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_CARDS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Trello: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    merged_query = {**query, "key": api_key, "token": api_token}
    try:
        response = await client.request(method, path, params=merged_query)
    except httpx.HTTPError as exc:
        logger.error("trello.request_failed", operation=operation, error=str(exc))
        msg = f"Trello: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_CARDS and isinstance(payload, list):
        result["cards"] = payload
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "trello.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Trello {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("trello.ok", operation=operation, status=response.status_code)
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
        raw = payload.get("raw")
        if isinstance(raw, str) and raw:
            return raw
    if isinstance(payload, str) and payload:
        return payload
    return f"HTTP {status_code}"
