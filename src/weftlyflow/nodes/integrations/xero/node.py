"""Xero node — invoices, contacts, and accounts via the Accounting API.

Dispatches to the Xero Accounting API (``/api.xro/2.0``) with the
distinctive *mandatory* ``xero-tenant-id`` header — one Xero app can be
connected to many organisations, so every request must declare which
one — sourced from
:class:`~weftlyflow.credentials.types.xero_api.XeroApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``list_invoices``, ``get_invoice``, ``create_invoice``,
  ``update_invoice``, ``list_contacts``, ``list_accounts``.
* ``invoice_id`` — target invoice UUID or number.
* ``document`` — invoice payload (wrapped in ``{"Invoices": [...]}``).
* ``where`` / ``order`` / ``statuses`` / ``ids`` — listing filters.
* ``page`` / ``page_size`` — listing pagination.

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
from weftlyflow.nodes.integrations.xero.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_INVOICE,
    OP_GET_INVOICE,
    OP_LIST_ACCOUNTS,
    OP_LIST_CONTACTS,
    OP_LIST_INVOICES,
    OP_UPDATE_INVOICE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.xero.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "xero_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.xero_api",)
_TENANT_HEADER: str = "xero-tenant-id"
_INVOICE_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_INVOICE, OP_UPDATE_INVOICE},
)
_DOCUMENT_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_INVOICE, OP_UPDATE_INVOICE},
)
_FILTER_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_INVOICES, OP_LIST_CONTACTS, OP_LIST_ACCOUNTS},
)

log = structlog.get_logger(__name__)


class XeroNode(BaseNode):
    """Dispatch a single Xero Accounting API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.xero",
        version=1,
        display_name="Xero",
        description="Manage Xero invoices, contacts, and accounts.",
        icon="icons/xero.svg",
        category=NodeCategory.INTEGRATION,
        group=["accounting", "finance"],
        documentation_url=(
            "https://developer.xero.com/documentation/api/accounting/overview"
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
                default=OP_LIST_INVOICES,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_INVOICES, label="List Invoices"),
                    PropertyOption(value=OP_GET_INVOICE, label="Get Invoice"),
                    PropertyOption(value=OP_CREATE_INVOICE, label="Create Invoice"),
                    PropertyOption(value=OP_UPDATE_INVOICE, label="Update Invoice"),
                    PropertyOption(value=OP_LIST_CONTACTS, label="List Contacts"),
                    PropertyOption(value=OP_LIST_ACCOUNTS, label="List Accounts"),
                ],
            ),
            PropertySchema(
                name="invoice_id",
                display_name="Invoice ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_INVOICE_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="document",
                display_name="Invoice Document",
                type="json",
                description='Xero invoice payload, e.g. {"Type": "ACCREC", ...}',
                display_options=DisplayOptions(
                    show={"operation": list(_DOCUMENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="where",
                display_name="Where Filter",
                type="string",
                description='Xero WHERE clause, e.g. Status=="AUTHORISED".',
                display_options=DisplayOptions(
                    show={"operation": list(_FILTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="order",
                display_name="Order By",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_FILTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="statuses",
                display_name="Statuses",
                type="string",
                description="Comma-separated statuses (e.g. DRAFT,AUTHORISED).",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_INVOICES]},
                ),
            ),
            PropertySchema(
                name="ids",
                display_name="Contact IDs",
                type="string",
                description="Comma-separated contact UUIDs.",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CONTACTS]},
                ),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_INVOICES, OP_LIST_CONTACTS]},
                ),
            ),
            PropertySchema(
                name="page_size",
                display_name="Page Size",
                type="number",
                description="Capped at 100 by Xero.",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_INVOICES]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Xero Accounting API call per input item."""
        token, tenant_id = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {token}",
            _TENANT_HEADER: tenant_id,
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
                        headers=headers,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Xero: a xero_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Xero: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    tenant_id = str(payload.get("tenant_id") or "").strip()
    if not tenant_id:
        msg = "Xero: credential has an empty 'tenant_id'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, tenant_id


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_INVOICES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Xero: unsupported operation {operation!r}"
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
        logger.error("xero.request_failed", operation=operation, error=str(exc))
        msg = f"Xero: network error on {operation}: {exc}"
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
            "xero.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Xero {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("xero.ok", operation=operation, status=response.status_code)
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
        detail = payload.get("Detail")
        if isinstance(detail, str) and detail:
            return detail
        message = payload.get("Message")
        if isinstance(message, str) and message:
            return message
        elements = payload.get("Elements")
        if isinstance(elements, list) and elements:
            first = elements[0]
            if isinstance(first, dict):
                validation = first.get("ValidationErrors")
                if isinstance(validation, list) and validation:
                    err = validation[0]
                    if isinstance(err, dict):
                        err_msg = err.get("Message")
                        if isinstance(err_msg, str) and err_msg:
                            return err_msg
    return f"HTTP {status_code}"
