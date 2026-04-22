"""HubSpot node — CRM v3 contact CRUD and search.

Dispatches to ``https://api.hubapi.com/crm/v3/objects/contacts[/{id}]``
with ``Authorization: Bearer <token>`` sourced from a
:class:`~weftlyflow.credentials.types.hubspot_private_app.HubSpotPrivateAppCredential`.

Parameters (all expression-capable):

* ``operation`` — ``create_contact``, ``update_contact``,
  ``get_contact``, ``delete_contact``, ``search_contacts``.
* ``contact_id`` — required for get/update/delete.
* ``properties`` — for create/update: JSON object of
  ``{"property_name": "value", ...}``. For get/search: comma-separated
  string or list of property names to fetch.
* ``query`` — free-text search for ``search_contacts``.
* ``filter_groups`` — HubSpot filter-group array.
* ``sorts`` — HubSpot sort array.
* ``limit`` — search page size (capped at 100).
* ``after`` — search pagination cursor.

Output: one item per input item with ``operation``, ``status``, the
parsed ``response`` body, and for ``search_contacts`` a convenience
``results`` list.
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
from weftlyflow.nodes.integrations.hubspot.constants import (
    API_BASE_URL,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_CONTACT,
    OP_DELETE_CONTACT,
    OP_GET_CONTACT,
    OP_SEARCH_CONTACTS,
    OP_UPDATE_CONTACT,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.hubspot.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "hubspot_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.hubspot_private_app",)
_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_CONTACT, OP_UPDATE_CONTACT, OP_DELETE_CONTACT},
)
_PROPERTIES_WRITE_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_CONTACT, OP_UPDATE_CONTACT},
)

log = structlog.get_logger(__name__)


class HubSpotNode(BaseNode):
    """Dispatch a single HubSpot CRM v3 contact call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.hubspot",
        version=1,
        display_name="HubSpot",
        description="Create, update, fetch, and search HubSpot CRM contacts.",
        icon="icons/hubspot.svg",
        category=NodeCategory.INTEGRATION,
        group=["crm"],
        documentation_url="https://developers.hubspot.com/docs/api/crm/contacts",
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
                default=OP_GET_CONTACT,
                required=True,
                options=[
                    PropertyOption(value=OP_CREATE_CONTACT, label="Create Contact"),
                    PropertyOption(value=OP_UPDATE_CONTACT, label="Update Contact"),
                    PropertyOption(value=OP_GET_CONTACT, label="Get Contact"),
                    PropertyOption(value=OP_DELETE_CONTACT, label="Delete Contact"),
                    PropertyOption(value=OP_SEARCH_CONTACTS, label="Search Contacts"),
                ],
            ),
            PropertySchema(
                name="contact_id",
                display_name="Contact ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="properties",
                display_name="Properties",
                type="json",
                description=(
                    "For create/update: object of property name→value. "
                    "For get/search: list or comma-separated string of "
                    "property names to fetch."
                ),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="string",
                description="Free-text search across indexed fields.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CONTACTS]}),
            ),
            PropertySchema(
                name="filter_groups",
                display_name="Filter Groups",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CONTACTS]}),
            ),
            PropertySchema(
                name="sorts",
                display_name="Sorts",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CONTACTS]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                default=DEFAULT_SEARCH_LIMIT,
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CONTACTS]}),
            ),
            PropertySchema(
                name="after",
                display_name="Pagination Cursor",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_CONTACTS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one HubSpot CRM call per input item."""
        token = await _resolve_token(ctx)
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
                        token=token,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_token(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "HubSpot: a hubspot_private_app credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "HubSpot: credential has an empty 'access_token'"
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
    operation = str(params.get("operation") or OP_GET_CONTACT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"HubSpot: unsupported operation {operation!r}"
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
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("hubspot.request_failed", operation=operation, error=str(exc))
        msg = f"HubSpot: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_SEARCH_CONTACTS and isinstance(payload, dict):
        results_list = payload.get("results", [])
        result["results"] = results_list if isinstance(results_list, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "hubspot.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"HubSpot {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("hubspot.ok", operation=operation, status=response.status_code)
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
        category = payload.get("category")
        if isinstance(category, str) and category:
            return category
    return f"HTTP {status_code}"
