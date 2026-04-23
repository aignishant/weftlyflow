"""ActiveCampaign node — contacts, lists, and tags via the v3 REST API.

Dispatches to the per-tenant base URL (resolved from the credential)
with the distinctive raw ``Api-Token`` header — no ``Bearer`` prefix —
sourced from
:class:`~weftlyflow.credentials.types.activecampaign_api.ActiveCampaignApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``list_contacts``, ``get_contact``, ``create_contact``,
  ``update_contact``, ``delete_contact``, ``add_contact_to_list``,
  ``add_tag_to_contact``, ``list_tags``.
* ``contact_id`` / ``list_id`` / ``tag_id`` — target resources.
* ``document`` — create/update payload (wrapped in ``{"contact": ...}``).
* ``status`` — list subscription status (1 active, 2 unsubscribed).
* ``email`` / ``search`` / ``limit`` / ``offset`` — list filters.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.activecampaign_api import base_url_from
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
from weftlyflow.nodes.integrations.activecampaign.constants import (
    API_TOKEN_HEADER,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_CONTACT_TO_LIST,
    OP_ADD_TAG_TO_CONTACT,
    OP_CREATE_CONTACT,
    OP_DELETE_CONTACT,
    OP_GET_CONTACT,
    OP_LIST_CONTACTS,
    OP_LIST_TAGS,
    OP_UPDATE_CONTACT,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.activecampaign.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "activecampaign_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.activecampaign_api",)
_CONTACT_ID_OPERATIONS: frozenset[str] = frozenset(
    {
        OP_GET_CONTACT,
        OP_UPDATE_CONTACT,
        OP_DELETE_CONTACT,
        OP_ADD_CONTACT_TO_LIST,
        OP_ADD_TAG_TO_CONTACT,
    },
)
_DOCUMENT_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_CONTACT, OP_UPDATE_CONTACT},
)
_PAGED_OPERATIONS: frozenset[str] = frozenset({OP_LIST_CONTACTS, OP_LIST_TAGS})

log = structlog.get_logger(__name__)


class ActiveCampaignNode(BaseNode):
    """Dispatch a single ActiveCampaign v3 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.activecampaign",
        version=1,
        display_name="ActiveCampaign",
        description="Manage ActiveCampaign contacts, lists, and tags.",
        icon="icons/activecampaign.svg",
        category=NodeCategory.INTEGRATION,
        group=["crm", "marketing"],
        documentation_url=(
            "https://developers.activecampaign.com/reference/overview"
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
                default=OP_LIST_CONTACTS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_CONTACTS, label="List Contacts"),
                    PropertyOption(value=OP_GET_CONTACT, label="Get Contact"),
                    PropertyOption(value=OP_CREATE_CONTACT, label="Create Contact"),
                    PropertyOption(value=OP_UPDATE_CONTACT, label="Update Contact"),
                    PropertyOption(value=OP_DELETE_CONTACT, label="Delete Contact"),
                    PropertyOption(
                        value=OP_ADD_CONTACT_TO_LIST,
                        label="Add Contact to List",
                    ),
                    PropertyOption(
                        value=OP_ADD_TAG_TO_CONTACT,
                        label="Add Tag to Contact",
                    ),
                    PropertyOption(value=OP_LIST_TAGS, label="List Tags"),
                ],
            ),
            PropertySchema(
                name="contact_id",
                display_name="Contact ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CONTACT_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="list_id",
                display_name="List ID",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_LIST_CONTACTS, OP_ADD_CONTACT_TO_LIST],
                    },
                ),
            ),
            PropertySchema(
                name="tag_id",
                display_name="Tag ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_ADD_TAG_TO_CONTACT]},
                ),
            ),
            PropertySchema(
                name="status",
                display_name="List Status",
                type="number",
                default=1,
                description="1 = subscribe, 2 = unsubscribe.",
                display_options=DisplayOptions(
                    show={"operation": [OP_ADD_CONTACT_TO_LIST]},
                ),
            ),
            PropertySchema(
                name="document",
                display_name="Contact Document",
                type="json",
                description='{"email": "...", "firstName": "...", ...}',
                display_options=DisplayOptions(
                    show={"operation": list(_DOCUMENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="email",
                display_name="Email Filter",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_CONTACTS]}),
            ),
            PropertySchema(
                name="search",
                display_name="Search",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CONTACTS, OP_LIST_TAGS]},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_PAGED_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset",
                type="number",
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
        """Issue one ActiveCampaign API call per input item."""
        token, raw_url = await _resolve_credentials(ctx)
        try:
            base_url = base_url_from(raw_url)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            API_TOKEN_HEADER: token,
            "Accept": "application/json",
        }
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
                        headers=headers,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "ActiveCampaign: an activecampaign_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("api_token") or "").strip()
    if not token:
        msg = "ActiveCampaign: credential has an empty 'api_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    url = str(payload.get("api_url") or "").strip()
    if not url:
        msg = "ActiveCampaign: credential has an empty 'api_url'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, url


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_CONTACTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"ActiveCampaign: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers = dict(headers)
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers=request_headers,
        )
    except httpx.HTTPError as exc:
        logger.error("activecampaign.request_failed", operation=operation, error=str(exc))
        msg = f"ActiveCampaign: network error on {operation}: {exc}"
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
            "activecampaign.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = (
            f"ActiveCampaign {operation} failed "
            f"(HTTP {response.status_code}): {error}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("activecampaign.ok", operation=operation, status=response.status_code)
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
            first = errors[0]
            if isinstance(first, dict):
                title = first.get("title")
                detail = first.get("detail")
                if isinstance(title, str) and isinstance(detail, str):
                    return f"{title}: {detail}"
                if isinstance(title, str) and title:
                    return title
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
