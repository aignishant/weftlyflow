"""PayPal node — orders, captures, refunds, and invoicing via the v2 API.

Dispatches to the environment-specific PayPal host
(``api-m.sandbox.paypal.com`` vs ``api-m.paypal.com``). The distinctive
shape is the **runtime token exchange**: rather than carrying a long-
lived bearer, the credential
:class:`~weftlyflow.credentials.types.paypal_api.PayPalApiCredential`
stores ``client_id`` + ``client_secret`` and the node fetches a fresh
access token (via OAuth2 client credentials grant) at the start of
each execution. Every write operation also carries a
``PayPal-Request-Id`` idempotency header.

Parameters (all expression-capable):

* ``operation`` — ``create_order``, ``get_order``, ``capture_order``,
  ``refund_capture``, ``list_invoices``, ``get_invoice``.
* ``intent`` / ``currency`` / ``amount`` / ``reference_id`` — order
  creation.
* ``order_id`` / ``capture_id`` / ``invoice_id`` — target resources.
* ``note_to_payer`` — refund detail.
* ``page`` / ``page_size`` / ``total_required`` — invoice pagination.
* ``request_id`` — explicit ``PayPal-Request-Id`` override (otherwise
  a per-call hex token is generated).

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.paypal_api import fetch_access_token, host_from
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
from weftlyflow.nodes.integrations.paypal.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CAPTURE_ORDER,
    OP_CREATE_ORDER,
    OP_GET_INVOICE,
    OP_GET_ORDER,
    OP_LIST_INVOICES,
    OP_REFUND_CAPTURE,
    REQUEST_ID_HEADER,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.paypal.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "paypal_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.paypal_api",)
_ORDER_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_ORDER, OP_CAPTURE_ORDER},
)

log = structlog.get_logger(__name__)


class PayPalNode(BaseNode):
    """Dispatch a single PayPal v2 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.paypal",
        version=1,
        display_name="PayPal",
        description="Create, capture, and refund PayPal v2 orders.",
        icon="icons/paypal.svg",
        category=NodeCategory.INTEGRATION,
        group=["payments", "commerce"],
        documentation_url="https://developer.paypal.com/api/rest/",
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
                default=OP_CREATE_ORDER,
                required=True,
                options=[
                    PropertyOption(value=OP_CREATE_ORDER, label="Create Order"),
                    PropertyOption(value=OP_GET_ORDER, label="Get Order"),
                    PropertyOption(value=OP_CAPTURE_ORDER, label="Capture Order"),
                    PropertyOption(value=OP_REFUND_CAPTURE, label="Refund Capture"),
                    PropertyOption(value=OP_LIST_INVOICES, label="List Invoices"),
                    PropertyOption(value=OP_GET_INVOICE, label="Get Invoice"),
                ],
            ),
            PropertySchema(
                name="intent",
                display_name="Intent",
                type="string",
                default="CAPTURE",
                description="CAPTURE | AUTHORIZE",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ORDER]},
                ),
            ),
            PropertySchema(
                name="currency",
                display_name="Currency Code",
                type="string",
                default="USD",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ORDER, OP_REFUND_CAPTURE]},
                ),
            ),
            PropertySchema(
                name="amount",
                display_name="Amount",
                type="string",
                description='Decimal string, e.g. "10.99".',
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ORDER, OP_REFUND_CAPTURE]},
                ),
            ),
            PropertySchema(
                name="reference_id",
                display_name="Reference ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ORDER]},
                ),
            ),
            PropertySchema(
                name="order_id",
                display_name="Order ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_ORDER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="capture_id",
                display_name="Capture ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_REFUND_CAPTURE]},
                ),
            ),
            PropertySchema(
                name="note_to_payer",
                display_name="Note to Payer",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_REFUND_CAPTURE]},
                ),
            ),
            PropertySchema(
                name="invoice_id",
                display_name="Invoice ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_INVOICE]},
                ),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_INVOICES]},
                ),
            ),
            PropertySchema(
                name="page_size",
                display_name="Page Size",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_INVOICES]},
                ),
            ),
            PropertySchema(
                name="total_required",
                display_name="Include Totals",
                type="boolean",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_INVOICES]},
                ),
            ),
            PropertySchema(
                name="request_id",
                display_name="PayPal-Request-Id Override",
                type="string",
                description="Auto-generated if blank — set for retry-safe writes.",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_CREATE_ORDER,
                            OP_CAPTURE_ORDER,
                            OP_REFUND_CAPTURE,
                        ],
                    },
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Fetch a runtime token then issue one PayPal v2 call per input item."""
        creds = await _resolve_credentials(ctx)
        try:
            host = host_from(str(creds.get("environment") or "live"))
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=f"https://{host}", timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            try:
                token = await fetch_access_token(client, creds)
            except (httpx.HTTPError, ValueError) as exc:
                raise NodeExecutionError(
                    f"PayPal: token fetch failed: {exc}",
                    node_id=ctx.node.id,
                    original=exc,
                ) from exc
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
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


async def _resolve_credentials(ctx: ExecutionContext) -> dict[str, Any]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "PayPal: a paypal_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    if not str(payload.get("client_id") or "").strip():
        msg = "PayPal: credential has an empty 'client_id'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not str(payload.get("client_secret") or "").strip():
        msg = "PayPal: credential has an empty 'client_secret'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_CREATE_ORDER).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"PayPal: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query, request_id = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers = dict(headers)
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    if request_id:
        request_headers[REQUEST_ID_HEADER] = request_id
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers=request_headers,
        )
    except httpx.HTTPError as exc:
        logger.error("paypal.request_failed", operation=operation, error=str(exc))
        msg = f"PayPal: network error on {operation}: {exc}"
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
            "paypal.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"PayPal {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("paypal.ok", operation=operation, status=response.status_code)
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
        details = payload.get("details")
        if isinstance(details, list) and details:
            first = details[0]
            if isinstance(first, dict):
                issue = first.get("issue") or first.get("description")
                if isinstance(issue, str) and issue:
                    return issue
        name = payload.get("name")
        if isinstance(name, str) and name:
            return name
    return f"HTTP {status_code}"
