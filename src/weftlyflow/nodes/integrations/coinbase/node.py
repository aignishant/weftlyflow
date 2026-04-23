"""Coinbase Exchange node — accounts, tickers, orders.

Dispatches against ``https://api.exchange.coinbase.com``. Authentication
is per-request HMAC signing driven by
:class:`~weftlyflow.credentials.types.coinbase_exchange.CoinbaseExchangeCredential`
— the credential computes ``CB-ACCESS-SIGN`` over the final request
line (``timestamp + method + path + body``) just before the call goes
out, so the node merely assembles the request and hands it to the
credential's :meth:`inject`.

Parameters (all expression-capable):

* ``operation`` — ``list_accounts`` / ``get_product_ticker`` /
  ``place_order`` / ``cancel_order``.
* ``product_id`` — e.g. ``BTC-USD``; required for ticker and order ops.
* ``side`` / ``order_type`` / ``price`` / ``size`` / ``funds`` /
  ``time_in_force`` / ``client_oid`` — order fields.
* ``order_id`` — required for cancel_order.

Output: one item per input item with ``operation``, ``status``, and
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
from weftlyflow.nodes.integrations.coinbase.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CANCEL_ORDER,
    OP_GET_PRODUCT_TICKER,
    OP_LIST_ACCOUNTS,
    OP_PLACE_ORDER,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.coinbase.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "coinbase_exchange"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.coinbase_exchange",)

log = structlog.get_logger(__name__)


class CoinbaseNode(BaseNode):
    """Dispatch a single Coinbase Exchange REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.coinbase",
        version=1,
        display_name="Coinbase Exchange",
        description="List accounts, read tickers, place and cancel orders on Coinbase Exchange.",
        icon="icons/coinbase.svg",
        category=NodeCategory.INTEGRATION,
        group=["finance"],
        documentation_url="https://docs.cdp.coinbase.com/exchange/docs/rest-api-overview",
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
                default=OP_LIST_ACCOUNTS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_ACCOUNTS, label="List Accounts"),
                    PropertyOption(value=OP_GET_PRODUCT_TICKER, label="Get Product Ticker"),
                    PropertyOption(value=OP_PLACE_ORDER, label="Place Order"),
                    PropertyOption(value=OP_CANCEL_ORDER, label="Cancel Order"),
                ],
            ),
            PropertySchema(
                name="product_id",
                display_name="Product ID",
                type="string",
                description='Trading pair, e.g. "BTC-USD".',
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_GET_PRODUCT_TICKER,
                            OP_PLACE_ORDER,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="side",
                display_name="Side",
                type="options",
                default=SIDE_BUY,
                options=[
                    PropertyOption(value=SIDE_BUY, label="Buy"),
                    PropertyOption(value=SIDE_SELL, label="Sell"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="order_type",
                display_name="Order Type",
                type="options",
                default=ORDER_TYPE_LIMIT,
                options=[
                    PropertyOption(value=ORDER_TYPE_LIMIT, label="Limit"),
                    PropertyOption(value=ORDER_TYPE_MARKET, label="Market"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="price",
                display_name="Price",
                type="string",
                description="Required for limit orders.",
                display_options=DisplayOptions(
                    show={"operation": [OP_PLACE_ORDER], "order_type": [ORDER_TYPE_LIMIT]},
                ),
            ),
            PropertySchema(
                name="size",
                display_name="Size (base currency)",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="funds",
                display_name="Funds (quote currency)",
                type="string",
                description="Alternative to size for market orders.",
                display_options=DisplayOptions(
                    show={"operation": [OP_PLACE_ORDER], "order_type": [ORDER_TYPE_MARKET]},
                ),
            ),
            PropertySchema(
                name="time_in_force",
                display_name="Time in Force",
                type="string",
                description="GTC, GTT, IOC, FOK (limit orders only).",
                display_options=DisplayOptions(
                    show={"operation": [OP_PLACE_ORDER], "order_type": [ORDER_TYPE_LIMIT]},
                ),
            ),
            PropertySchema(
                name="client_oid",
                display_name="Client Order ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="order_id",
                display_name="Order ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CANCEL_ORDER]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Coinbase Exchange call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, injector=injector,
                        creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Coinbase: a coinbase_exchange credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    for key in ("api_key", "api_secret", "passphrase"):
        if not str(payload.get(key) or "").strip():
            msg = f"Coinbase: credential has an empty {key!r}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_ACCOUNTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Coinbase: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = client.build_request(
        method, path, params=query or None, json=body, headers=headers,
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("coinbase.request_failed", operation=operation, error=str(exc))
        msg = f"Coinbase: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    parsed = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": parsed,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(parsed, response.status_code)
        logger.warning(
            "coinbase.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Coinbase {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("coinbase.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, dict):
        for key in ("message", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
