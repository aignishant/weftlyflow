"""Microsoft Graph node — directory and Outlook read/write over OData.

Dispatches to ``graph.microsoft.com/v1.0`` with ``Authorization: Bearer
<access_token>`` sourced from
:class:`~weftlyflow.credentials.types.microsoft_graph.MicrosoftGraphCredential`.

The distinctive shape here is the conditional
``ConsistencyLevel: eventual`` header that Graph requires for
advanced-query list calls (``$search``, ``$count``, and certain
``$filter`` operators like ``endswith`` / ``ne``). The node emits that
header *only* on operations whose query parameters opt into advanced
mode — determined by
:func:`~weftlyflow.nodes.integrations.microsoft_graph.operations.build_request`.

Parameters (all expression-capable):

* ``operation`` — ``list_users``, ``get_user``, ``list_messages``,
  ``send_mail``, ``list_events``, ``create_event``.
* ``user_id`` — directory principal (``me`` for token owner).
* ``select`` / ``filter`` / ``search`` / ``order_by`` / ``count`` /
  ``top`` / ``skip_token`` — OData list paging.
* ``message`` / ``save_to_sent_items`` — send_mail inputs.
* ``event`` — create_event payload.

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
from weftlyflow.nodes.integrations.microsoft_graph.constants import (
    API_BASE_URL,
    CONSISTENCY_LEVEL_EVENTUAL,
    CONSISTENCY_LEVEL_HEADER,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_EVENT,
    OP_GET_USER,
    OP_LIST_EVENTS,
    OP_LIST_MESSAGES,
    OP_LIST_USERS,
    OP_SEND_MAIL,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.microsoft_graph.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "microsoft_graph"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.microsoft_graph",)
_LIST_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_USERS, OP_LIST_MESSAGES, OP_LIST_EVENTS},
)
_MAILBOX_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_MESSAGES, OP_SEND_MAIL, OP_LIST_EVENTS, OP_CREATE_EVENT},
)
_USER_TARGET_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_USER, *_MAILBOX_OPERATIONS},
)

log = structlog.get_logger(__name__)


class MicrosoftGraphNode(BaseNode):
    """Dispatch a single Microsoft Graph call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.microsoft_graph",
        version=1,
        display_name="Microsoft Graph",
        description="Query Azure AD directory and Outlook mail/calendar via Graph.",
        icon="icons/microsoft.svg",
        category=NodeCategory.INTEGRATION,
        group=["microsoft", "productivity"],
        documentation_url="https://learn.microsoft.com/en-us/graph/api/overview",
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
                default=OP_LIST_USERS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_USERS, label="List Users"),
                    PropertyOption(value=OP_GET_USER, label="Get User"),
                    PropertyOption(value=OP_LIST_MESSAGES, label="List Messages"),
                    PropertyOption(value=OP_SEND_MAIL, label="Send Mail"),
                    PropertyOption(value=OP_LIST_EVENTS, label="List Events"),
                    PropertyOption(value=OP_CREATE_EVENT, label="Create Event"),
                ],
            ),
            PropertySchema(
                name="user_id",
                display_name="User",
                type="string",
                default="me",
                description="User principal ('me' for token owner).",
                display_options=DisplayOptions(
                    show={"operation": list(_USER_TARGET_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="select",
                display_name="Select",
                type="string",
                description="Comma-separated $select projection.",
                display_options=DisplayOptions(
                    show={"operation": [*_LIST_OPERATIONS, OP_GET_USER]},
                ),
            ),
            PropertySchema(
                name="filter",
                display_name="Filter",
                type="string",
                description="OData $filter expression.",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="search",
                display_name="Search",
                type="string",
                description="Advanced-query $search — triggers ConsistencyLevel: eventual.",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="order_by",
                display_name="Order By",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="count",
                display_name="Include Count",
                type="boolean",
                description="Append $count=true — triggers ConsistencyLevel: eventual.",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="top",
                display_name="Page Size",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="skip_token",
                display_name="Skip Token",
                type="string",
                description="Opaque cursor from the previous page.",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="message",
                display_name="Message",
                type="json",
                description="Outlook message payload (subject/body/toRecipients/…).",
                display_options=DisplayOptions(show={"operation": [OP_SEND_MAIL]}),
            ),
            PropertySchema(
                name="save_to_sent_items",
                display_name="Save to Sent Items",
                type="boolean",
                display_options=DisplayOptions(show={"operation": [OP_SEND_MAIL]}),
            ),
            PropertySchema(
                name="event",
                display_name="Event",
                type="json",
                description="Calendar event payload.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_EVENT]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Microsoft Graph call per input item."""
        access_token = await _resolve_credential(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        base_headers = {
            "Authorization": f"Bearer {access_token}",
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
                        base_headers=base_headers,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credential(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Microsoft Graph: a microsoft_graph credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Microsoft Graph: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    base_headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_USERS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Microsoft Graph: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query, advanced = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers = dict(base_headers)
    if advanced:
        headers[CONSISTENCY_LEVEL_HEADER] = CONSISTENCY_LEVEL_EVENTUAL
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.error(
            "microsoft_graph.request_failed", operation=operation, error=str(exc),
        )
        msg = f"Microsoft Graph: network error on {operation}: {exc}"
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
            "microsoft_graph.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = (
            f"Microsoft Graph {operation} failed "
            f"(HTTP {response.status_code}): {error}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info(
        "microsoft_graph.ok", operation=operation, status=response.status_code,
    )
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
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            code = error.get("code")
            if isinstance(message, str) and isinstance(code, str):
                return f"{code}: {message}"
            if isinstance(message, str) and message:
                return message
            if isinstance(code, str) and code:
                return code
        if isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"
