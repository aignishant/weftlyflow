"""Zoho CRM node — v6 REST API for modules and records.

Dispatches to the DC-specific Zoho host (``https://www.zohoapis.<tld>``)
with the distinctive ``Authorization: Zoho-oauthtoken <token>`` header
(note: not ``Bearer``) sourced from
:class:`~weftlyflow.credentials.types.zoho_crm_oauth2.ZohoCrmOAuth2Credential`.
The datacenter segment is read from the credential and mapped to the
API host via
:func:`weftlyflow.credentials.types.zoho_crm_oauth2.host_for`.

Parameters (all expression-capable):

* ``operation`` — ``list_records``, ``get_record``, ``create_record``,
  ``update_record``, ``delete_record``, ``search_records``.
* ``module`` — Zoho module API name (e.g. ``Leads``, ``Contacts``).
* ``record_id`` — target record (get/update/delete).
* ``fields`` — JSON body for create/update.
* ``trigger`` — optional workflow triggers for create.
* ``criteria`` / ``email`` / ``phone`` / ``word`` — search inputs
  (exactly one is required).
* ``per_page`` / ``page`` — list/search paging.
* ``sort_by`` / ``sort_order`` — list ordering.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``. List and search operations surface a convenience
``data`` list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.zoho_crm_oauth2 import host_for
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
from weftlyflow.nodes.integrations.zoho_crm.constants import (
    DEFAULT_PER_PAGE,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_RECORD,
    OP_DELETE_RECORD,
    OP_GET_RECORD,
    OP_LIST_RECORDS,
    OP_SEARCH_RECORDS,
    OP_UPDATE_RECORD,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.zoho_crm.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "zoho_crm_oauth2"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.zoho_crm_oauth2",)
_RECORD_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_RECORD, OP_UPDATE_RECORD, OP_DELETE_RECORD},
)
_FIELDS_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_RECORD, OP_UPDATE_RECORD},
)
_DATA_RESPONSE_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_RECORDS, OP_SEARCH_RECORDS},
)

log = structlog.get_logger(__name__)


class ZohoCrmNode(BaseNode):
    """Dispatch a single Zoho CRM v6 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.zoho_crm",
        version=1,
        display_name="Zoho CRM",
        description="Manage Zoho CRM modules and records.",
        icon="icons/zoho_crm.svg",
        category=NodeCategory.INTEGRATION,
        group=["crm", "sales"],
        documentation_url="https://www.zoho.com/crm/developer/docs/api/v6/",
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
                default=OP_LIST_RECORDS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_RECORDS, label="List Records"),
                    PropertyOption(value=OP_GET_RECORD, label="Get Record"),
                    PropertyOption(value=OP_CREATE_RECORD, label="Create Record"),
                    PropertyOption(value=OP_UPDATE_RECORD, label="Update Record"),
                    PropertyOption(value=OP_DELETE_RECORD, label="Delete Record"),
                    PropertyOption(value=OP_SEARCH_RECORDS, label="Search Records"),
                ],
            ),
            PropertySchema(
                name="module",
                display_name="Module",
                type="string",
                required=True,
                description="API name of the Zoho module (Leads, Contacts, Deals...).",
            ),
            PropertySchema(
                name="record_id",
                display_name="Record ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_RECORD_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="JSON of field values for create/update.",
                display_options=DisplayOptions(
                    show={"operation": list(_FIELDS_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="trigger",
                display_name="Triggers",
                type="string",
                description="Comma-separated triggers (approval, workflow, blueprint).",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_RECORD]}),
            ),
            PropertySchema(
                name="criteria",
                display_name="Criteria",
                type="string",
                description="COQL-style filter, e.g. ``(Last_Name:equals:Doe)``.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_RECORDS]}),
            ),
            PropertySchema(
                name="email",
                display_name="Email",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_RECORDS]}),
            ),
            PropertySchema(
                name="phone",
                display_name="Phone",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_RECORDS]}),
            ),
            PropertySchema(
                name="word",
                display_name="Word",
                type="string",
                description="Free-text search term.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_RECORDS]}),
            ),
            PropertySchema(
                name="per_page",
                display_name="Per Page",
                type="number",
                default=DEFAULT_PER_PAGE,
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_RECORDS, OP_SEARCH_RECORDS]},
                ),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_RECORDS, OP_SEARCH_RECORDS]},
                ),
            ),
            PropertySchema(
                name="sort_by",
                display_name="Sort By",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="sort_order",
                display_name="Sort Order",
                type="options",
                options=[
                    PropertyOption(value="asc", label="Ascending"),
                    PropertyOption(value="desc", label="Descending"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="fields_filter",
                display_name="Fields Filter",
                type="string",
                description="Comma-separated field API names to return.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Zoho CRM REST call per input item."""
        token, datacenter = await _resolve_credentials(ctx)
        try:
            host = host_for(datacenter)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        base_url = f"https://{host}"
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS,
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
        msg = "Zoho: a zoho_crm_oauth2 credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Zoho: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    datacenter = str(payload.get("datacenter") or "us").strip().lower()
    return token, datacenter


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_RECORDS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Zoho: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    forwarded = _normalize_fields_filter(params)
    try:
        method, path, body, query = build_request(operation, forwarded)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers={
                "Authorization": f"Zoho-oauthtoken {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("zoho_crm.request_failed", operation=operation, error=str(exc))
        msg = f"Zoho: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation in _DATA_RESPONSE_OPERATIONS and isinstance(payload, dict):
        data = payload.get("data", [])
        result["data"] = data if isinstance(data, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "zoho_crm.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Zoho {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("zoho_crm.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _normalize_fields_filter(params: dict[str, Any]) -> dict[str, Any]:
    fields_filter = params.get("fields_filter")
    if fields_filter in (None, ""):
        return params
    if params.get("fields") is not None:
        return params
    forwarded = dict(params)
    forwarded["fields"] = fields_filter
    return forwarded


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        code = payload.get("code")
        message = payload.get("message")
        if isinstance(message, str) and message:
            return f"{code}: {message}" if code else message
    return f"HTTP {status_code}"
