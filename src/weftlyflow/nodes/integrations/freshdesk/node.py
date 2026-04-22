"""Freshdesk node — v2 REST API for tickets and contacts.

Dispatches to ``<subdomain>.freshdesk.com/api/v2`` with HTTP Basic auth
where the api_key is the username and the password is literally
``X`` — a Freshdesk convention sourced from
:class:`~weftlyflow.credentials.types.freshdesk_api.FreshdeskApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``list_tickets``, ``get_ticket``, ``create_ticket``,
  ``update_ticket``, ``list_contacts``, ``create_contact``.
* ``ticket_id`` — target ticket (get/update).
* ``subject`` / ``description`` / ``email`` — ``create_ticket``.
* ``priority`` / ``status`` / ``source`` — enums (label or integer).
* ``type`` / ``tags`` — optional ticket extras.
* ``fields`` — JSON patch body for ``update_ticket``.
* ``name`` / ``phone`` / ``mobile`` / ``company_id`` —
  ``create_contact``.
* ``per_page`` / ``page`` / ``updated_since`` — list paging.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.freshdesk_api import base_url_for, basic_auth_header
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
from weftlyflow.nodes.integrations.freshdesk.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_CONTACT,
    OP_CREATE_TICKET,
    OP_GET_TICKET,
    OP_LIST_CONTACTS,
    OP_LIST_TICKETS,
    OP_UPDATE_TICKET,
    SUPPORTED_OPERATIONS,
    TICKET_PRIORITIES,
    TICKET_SOURCES,
    TICKET_STATUSES,
)
from weftlyflow.nodes.integrations.freshdesk.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "freshdesk_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.freshdesk_api",)
_TICKET_ID_OPERATIONS: frozenset[str] = frozenset({OP_GET_TICKET, OP_UPDATE_TICKET})

log = structlog.get_logger(__name__)


class FreshdeskNode(BaseNode):
    """Dispatch a single Freshdesk v2 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.freshdesk",
        version=1,
        display_name="Freshdesk",
        description="Create and manage Freshdesk tickets and contacts.",
        icon="icons/freshdesk.svg",
        category=NodeCategory.INTEGRATION,
        group=["support", "helpdesk"],
        documentation_url="https://developers.freshdesk.com/api/",
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
                default=OP_LIST_TICKETS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_TICKETS, label="List Tickets"),
                    PropertyOption(value=OP_GET_TICKET, label="Get Ticket"),
                    PropertyOption(value=OP_CREATE_TICKET, label="Create Ticket"),
                    PropertyOption(value=OP_UPDATE_TICKET, label="Update Ticket"),
                    PropertyOption(value=OP_LIST_CONTACTS, label="List Contacts"),
                    PropertyOption(value=OP_CREATE_CONTACT, label="Create Contact"),
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
                name="description",
                display_name="Description",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="email",
                display_name="Email",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_CREATE_TICKET,
                            OP_CREATE_CONTACT,
                            OP_LIST_CONTACTS,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="priority",
                display_name="Priority",
                type="options",
                default="medium",
                options=[
                    PropertyOption(value=label, label=label.capitalize())
                    for label in TICKET_PRIORITIES
                ],
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="status",
                display_name="Status",
                type="options",
                default="open",
                options=[
                    PropertyOption(value=label, label=label.capitalize())
                    for label in TICKET_STATUSES
                ],
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="source",
                display_name="Source",
                type="options",
                options=[
                    PropertyOption(value=label, label=label.replace("_", " ").title())
                    for label in TICKET_SOURCES
                ],
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="type",
                display_name="Type",
                type="string",
                description="Freshdesk ticket type label.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="tags",
                display_name="Tags",
                type="string",
                description="Comma-separated tag list.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TICKET]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="JSON patch body for update_ticket.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_TICKET]}),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="phone",
                display_name="Phone",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="mobile",
                display_name="Mobile",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="company_id",
                display_name="Company ID",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CONTACT]}),
            ),
            PropertySchema(
                name="per_page",
                display_name="Per Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_TICKETS, OP_LIST_CONTACTS]},
                ),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_TICKETS, OP_LIST_CONTACTS]},
                ),
            ),
            PropertySchema(
                name="updated_since",
                display_name="Updated Since",
                type="string",
                description="ISO-8601 timestamp to filter list_tickets.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TICKETS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Freshdesk REST call per input item."""
        api_key, subdomain = await _resolve_credentials(ctx)
        try:
            base_url = base_url_for(subdomain)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        auth_header = basic_auth_header(api_key)
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
                        auth_header=auth_header,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Freshdesk: a freshdesk_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "Freshdesk: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    subdomain = str(payload.get("subdomain") or "").strip()
    if not subdomain:
        msg = "Freshdesk: credential has an empty 'subdomain'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return api_key, subdomain


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    auth_header: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_TICKETS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Freshdesk: unsupported operation {operation!r}"
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
        logger.error("freshdesk.request_failed", operation=operation, error=str(exc))
        msg = f"Freshdesk: network error on {operation}: {exc}"
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
            "freshdesk.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Freshdesk {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("freshdesk.ok", operation=operation, status=response.status_code)
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
        errors = payload.get("errors")
        if isinstance(description, str) and description:
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    msg = first.get("message")
                    if isinstance(msg, str) and msg:
                        return f"{description}: {msg}"
            return description
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
