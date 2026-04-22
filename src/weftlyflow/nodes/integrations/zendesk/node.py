"""Zendesk node — Support v2 REST API for tickets and comments.

Dispatches to ``https://<subdomain>.zendesk.com/api/v2/...`` with HTTP
Basic authentication (``<email>/token`` username + API token password)
sourced from
:class:`~weftlyflow.credentials.types.zendesk_api.ZendeskApiCredential`.
The tenant subdomain lives on the credential so multiple environments
reuse one workflow definition.

Parameters (all expression-capable):

* ``operation`` — ``get_ticket``, ``create_ticket``, ``update_ticket``,
  ``list_tickets``, ``add_comment``, ``search``.
* ``ticket_id`` — for get/update/add_comment.
* ``subject`` / ``comment`` / ``priority`` / ``extra_fields`` — for
  ``create_ticket``.
* ``fields`` — JSON of updates for ``update_ticket``.
* ``per_page`` / ``page`` — pagination for ``list_tickets``.
* ``public`` — comment visibility boolean on ``add_comment``.
* ``query`` / ``sort_by`` / ``sort_order`` — for ``search``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``; ``list_tickets`` and ``search`` also surface a
convenience ``results`` list.
"""

from __future__ import annotations

import base64
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
from weftlyflow.nodes.integrations.zendesk.constants import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_COMMENT,
    OP_CREATE_TICKET,
    OP_GET_TICKET,
    OP_LIST_TICKETS,
    OP_SEARCH,
    OP_UPDATE_TICKET,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.zendesk.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "zendesk_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.zendesk_api",)
_TICKET_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_TICKET, OP_UPDATE_TICKET, OP_ADD_COMMENT},
)

log = structlog.get_logger(__name__)


class ZendeskNode(BaseNode):
    """Dispatch a single Zendesk Support REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.zendesk",
        version=1,
        display_name="Zendesk",
        description="Manage Zendesk Support tickets and comments.",
        icon="icons/zendesk.svg",
        category=NodeCategory.INTEGRATION,
        group=["crm", "support"],
        documentation_url=(
            "https://developer.zendesk.com/api-reference/ticketing/introduction/"
        ),
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
                default=OP_GET_TICKET,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_TICKET, label="Get Ticket"),
                    PropertyOption(value=OP_CREATE_TICKET, label="Create Ticket"),
                    PropertyOption(value=OP_UPDATE_TICKET, label="Update Ticket"),
                    PropertyOption(value=OP_LIST_TICKETS, label="List Tickets"),
                    PropertyOption(value=OP_ADD_COMMENT, label="Add Comment"),
                    PropertyOption(value=OP_SEARCH, label="Search"),
                ],
            ),
            PropertySchema(
                name="ticket_id",
                display_name="Ticket ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_TICKET_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="subject",
                display_name="Subject",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="comment",
                display_name="Comment",
                type="string",
                description="Comment body for ticket creation or add_comment.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_TICKET, OP_ADD_COMMENT]},
                ),
            ),
            PropertySchema(
                name="public",
                display_name="Public",
                type="boolean",
                default=True,
                display_options=DisplayOptions(show={"operation": [OP_ADD_COMMENT]}),
            ),
            PropertySchema(
                name="priority",
                display_name="Priority",
                type="options",
                options=[
                    PropertyOption(value="urgent", label="Urgent"),
                    PropertyOption(value="high", label="High"),
                    PropertyOption(value="normal", label="Normal"),
                    PropertyOption(value="low", label="Low"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="extra_fields",
                display_name="Extra Fields",
                type="json",
                description="Optional JSON merged into the ticket body.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_TICKET]}),
            ),
            PropertySchema(
                name="per_page",
                display_name="Per Page",
                type="number",
                default=DEFAULT_LIST_LIMIT,
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_TICKETS, OP_SEARCH]},
                ),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TICKETS]}),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="string",
                description="Zendesk search syntax (e.g. 'status:open type:ticket').",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="sort_by",
                display_name="Sort By",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="sort_order",
                display_name="Sort Order",
                type="options",
                options=[
                    PropertyOption(value="asc", label="Ascending"),
                    PropertyOption(value="desc", label="Descending"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Zendesk REST call per input item."""
        subdomain, auth_header = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        base_url = f"https://{subdomain}.zendesk.com"
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
                        auth_header=auth_header,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Zendesk: a zendesk_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    subdomain = str(payload.get("subdomain") or "").strip().lower()
    email = str(payload.get("email") or "").strip()
    token = str(payload.get("api_token") or "").strip()
    if not subdomain or not email or not token:
        msg = "Zendesk: credential must have 'subdomain', 'email', and 'api_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    encoded = base64.b64encode(f"{email}/token:{token}".encode()).decode("ascii")
    return subdomain, f"Basic {encoded}"


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    auth_header: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_GET_TICKET).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Zendesk: unsupported operation {operation!r}"
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
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("zendesk.request_failed", operation=operation, error=str(exc))
        msg = f"Zendesk: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_TICKETS and isinstance(payload, dict):
        tickets = payload.get("tickets", [])
        result["results"] = tickets if isinstance(tickets, list) else []
    elif operation == OP_SEARCH and isinstance(payload, dict):
        hits = payload.get("results", [])
        result["results"] = hits if isinstance(hits, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "zendesk.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Zendesk {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("zendesk.ok", operation=operation, status=response.status_code)
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
        details = payload.get("details")
        if isinstance(details, dict) and details:
            parts: list[str] = []
            for field, entries in details.items():
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict):
                            message = entry.get("description") or entry.get("message")
                            if message:
                                parts.append(f"{field}: {message}")
            if parts:
                return "; ".join(parts)
        error = payload.get("error")
        if isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"
