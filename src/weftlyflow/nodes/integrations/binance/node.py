"""Binance Spot node — account, tickers, orders.

Dispatches against ``api.binance.com`` (or the testnet host for
sandbox testing). Public endpoints (ticker price) ride the plain
API-key header from
:class:`~weftlyflow.credentials.types.binance_api.BinanceApiCredential`;
signed endpoints (account, place/cancel order) append a millisecond
``timestamp`` and a hex-encoded HMAC-SHA256 ``signature`` to the
query string before the request goes out.

Parameters (all expression-capable):

* ``operation``  — ``account_info`` / ``get_ticker_price`` /
  ``place_order`` / ``cancel_order``.
* ``symbol``     — trading pair, e.g. ``BTCUSDT``.
* ``side`` / ``order_type`` / ``price`` / ``quantity`` /
  ``quote_order_qty`` / ``time_in_force`` / ``client_order_id`` —
  order fields.
* ``order_id`` / ``orig_client_order_id`` — cancel targeting.
* ``recv_window`` — optional integer ms, mirrors Binance's param.

Output: one item per input item with ``operation``, ``status``, and
parsed ``response``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlencode

import httpx
import structlog

from weftlyflow.credentials.types.binance_api import host_for, sign_query
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
from weftlyflow.nodes.integrations.binance.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_ACCOUNT_INFO,
    OP_CANCEL_ORDER,
    OP_GET_TICKER_PRICE,
    OP_PLACE_ORDER,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.binance.operations import build_request, is_signed

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "binance_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.binance_api",)

log = structlog.get_logger(__name__)


class BinanceNode(BaseNode):
    """Dispatch a single Binance Spot REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.binance",
        version=1,
        display_name="Binance Spot",
        description="Account, tickers, and order management on Binance Spot.",
        icon="icons/binance.svg",
        category=NodeCategory.INTEGRATION,
        group=["finance"],
        documentation_url=(
            "https://developers.binance.com/docs/binance-spot-api-docs/rest-api"
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
                default=OP_ACCOUNT_INFO,
                required=True,
                options=[
                    PropertyOption(value=OP_ACCOUNT_INFO, label="Account Info"),
                    PropertyOption(value=OP_GET_TICKER_PRICE, label="Get Ticker Price"),
                    PropertyOption(value=OP_PLACE_ORDER, label="Place Order"),
                    PropertyOption(value=OP_CANCEL_ORDER, label="Cancel Order"),
                ],
            ),
            PropertySchema(
                name="symbol",
                display_name="Symbol",
                type="string",
                description='Trading pair, e.g. "BTCUSDT".',
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_GET_TICKER_PRICE,
                            OP_PLACE_ORDER,
                            OP_CANCEL_ORDER,
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
                name="quantity",
                display_name="Quantity (base asset)",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="quote_order_qty",
                display_name="Quote Order Qty",
                type="string",
                description="Alternative to quantity for market orders (quote asset).",
                display_options=DisplayOptions(
                    show={"operation": [OP_PLACE_ORDER], "order_type": [ORDER_TYPE_MARKET]},
                ),
            ),
            PropertySchema(
                name="time_in_force",
                display_name="Time in Force",
                type="string",
                default="GTC",
                description="GTC, IOC, FOK (limit orders only).",
                display_options=DisplayOptions(
                    show={"operation": [OP_PLACE_ORDER], "order_type": [ORDER_TYPE_LIMIT]},
                ),
            ),
            PropertySchema(
                name="client_order_id",
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
            PropertySchema(
                name="orig_client_order_id",
                display_name="Original Client Order ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CANCEL_ORDER]}),
            ),
            PropertySchema(
                name="recv_window",
                display_name="Receive Window (ms)",
                type="number",
                description="Optional — limit request validity window on the server.",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_ACCOUNT_INFO,
                            OP_PLACE_ORDER,
                            OP_CANCEL_ORDER,
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
        """Issue one Binance Spot call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        host = host_for(payload.get("environment"))
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=host, timeout=DEFAULT_TIMEOUT_SECONDS,
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
        msg = "Binance: a binance_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    for key in ("api_key", "api_secret"):
        if not str(payload.get(key) or "").strip():
            msg = f"Binance: credential has an empty {key!r}"
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
    operation = str(params.get("operation") or OP_ACCOUNT_INFO).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Binance: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    recv_window = str(params.get("recv_window") or "").strip()
    if is_signed(operation):
        if recv_window:
            query["recvWindow"] = recv_window
        query["timestamp"] = str(int(time.time() * 1000))
        total_params = urlencode(query)
        signature = sign_query(
            api_secret=str(creds.get("api_secret", "")),
            total_params=total_params,
        )
        query["signature"] = signature
    request = client.build_request(
        method, path, params=query or None, headers={"Accept": "application/json"},
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("binance.request_failed", operation=operation, error=str(exc))
        msg = f"Binance: network error on {operation}: {exc}"
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
            "binance.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Binance {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("binance.ok", operation=operation, status=response.status_code)
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
        for key in ("msg", "message", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
