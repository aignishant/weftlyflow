"""Square node — customers, payments, and order search via the v2 REST API.

Dispatches to the Square API on the environment-specific host
(``connect.squareupsandbox.com`` vs ``connect.squareup.com``) with the
distinctive **mandatory** ``Square-Version: YYYY-MM-DD`` header — Square
explicitly version-pins every request. The version is stored on the
credential
(:class:`~weftlyflow.credentials.types.square_api.SquareApiCredential`)
so all node calls inherit a single deterministic API contract.

Parameters (all expression-capable):

* ``operation`` — ``list_customers``, ``get_customer``,
  ``create_customer``, ``list_payments``, ``create_payment``,
  ``search_orders``.
* ``customer_id`` — target customer.
* ``document`` — customer body (create).
* ``cursor`` / ``limit`` — pagination.
* ``begin_time`` / ``end_time`` / ``location_id`` — payment filters.
* ``source_id`` / ``amount`` / ``currency`` / ``idempotency_key`` —
  payment creation.
* ``location_ids`` / ``query`` — order search.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.square_api import host_from
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
from weftlyflow.nodes.integrations.square.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_CUSTOMER,
    OP_CREATE_PAYMENT,
    OP_GET_CUSTOMER,
    OP_LIST_CUSTOMERS,
    OP_LIST_PAYMENTS,
    OP_SEARCH_ORDERS,
    SUPPORTED_OPERATIONS,
    VERSION_HEADER,
)
from weftlyflow.nodes.integrations.square.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "square_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.square_api",)

log = structlog.get_logger(__name__)


class SquareNode(BaseNode):
    """Dispatch a single Square v2 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.square",
        version=1,
        display_name="Square",
        description="Manage Square customers, payments, and orders.",
        icon="icons/square.svg",
        category=NodeCategory.INTEGRATION,
        group=["payments", "commerce"],
        documentation_url="https://developer.squareup.com/reference/square",
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
                default=OP_LIST_CUSTOMERS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_CUSTOMERS, label="List Customers"),
                    PropertyOption(value=OP_GET_CUSTOMER, label="Get Customer"),
                    PropertyOption(value=OP_CREATE_CUSTOMER, label="Create Customer"),
                    PropertyOption(value=OP_LIST_PAYMENTS, label="List Payments"),
                    PropertyOption(value=OP_CREATE_PAYMENT, label="Create Payment"),
                    PropertyOption(value=OP_SEARCH_ORDERS, label="Search Orders"),
                ],
            ),
            PropertySchema(
                name="customer_id",
                display_name="Customer ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_CUSTOMER]},
                ),
            ),
            PropertySchema(
                name="document",
                display_name="Customer Document",
                type="json",
                description='{"given_name": "...", "email_address": "...", ...}',
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_CUSTOMER]},
                ),
            ),
            PropertySchema(
                name="cursor",
                display_name="Cursor",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_CUSTOMERS,
                            OP_LIST_PAYMENTS,
                            OP_SEARCH_ORDERS,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_CUSTOMERS,
                            OP_LIST_PAYMENTS,
                            OP_SEARCH_ORDERS,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="begin_time",
                display_name="Begin Time (RFC3339)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_PAYMENTS]},
                ),
            ),
            PropertySchema(
                name="end_time",
                display_name="End Time (RFC3339)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_PAYMENTS]},
                ),
            ),
            PropertySchema(
                name="location_id",
                display_name="Location ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_PAYMENTS, OP_CREATE_PAYMENT]},
                ),
            ),
            PropertySchema(
                name="source_id",
                display_name="Source ID",
                type="string",
                description="Tokenized card or wallet source.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PAYMENT]},
                ),
            ),
            PropertySchema(
                name="amount",
                display_name="Amount (smallest unit)",
                type="number",
                description="e.g. 1099 = $10.99 USD.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PAYMENT]},
                ),
            ),
            PropertySchema(
                name="currency",
                display_name="Currency",
                type="string",
                default="USD",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PAYMENT]},
                ),
            ),
            PropertySchema(
                name="idempotency_key",
                display_name="Idempotency Key",
                type="string",
                description="Auto-generated if blank — override for retry safety.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PAYMENT]},
                ),
            ),
            PropertySchema(
                name="location_ids",
                display_name="Location IDs",
                type="string",
                description="Comma-separated location ids or JSON list.",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEARCH_ORDERS]},
                ),
            ),
            PropertySchema(
                name="query",
                display_name="Query Filter",
                type="json",
                description="Square SearchOrders 'query' object.",
                display_options=DisplayOptions(
                    show={"operation": [OP_SEARCH_ORDERS]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Square v2 call per input item."""
        token, version, host = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {token}",
            VERSION_HEADER: version,
            "Accept": "application/json",
        }
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=f"https://{host}", timeout=DEFAULT_TIMEOUT_SECONDS,
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


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Square: a square_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Square: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    version = str(payload.get("api_version") or "").strip()
    if not version:
        msg = "Square: credential has an empty 'api_version'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    environment = str(payload.get("environment") or "production").strip()
    try:
        host = host_from(environment)
    except ValueError as exc:
        raise NodeExecutionError(
            str(exc), node_id=ctx.node.id, original=exc,
        ) from exc
    return token, version, host


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_CUSTOMERS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Square: unsupported operation {operation!r}"
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
        logger.error("square.request_failed", operation=operation, error=str(exc))
        msg = f"Square: network error on {operation}: {exc}"
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
            "square.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Square {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("square.ok", operation=operation, status=response.status_code)
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
                detail = first.get("detail") or first.get("code")
                if isinstance(detail, str) and detail:
                    return detail
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
