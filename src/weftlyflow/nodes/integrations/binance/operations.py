"""Per-operation request builders for the Binance Spot node.

Each builder returns ``(http_method, path, query)`` — Binance SIGNED
endpoints carry their payload entirely in the query string (the REST
docs refer to a ``body`` parameter but in practice every field can be
sent as a query param, so we pick one encoding and stick with it).
The node appends ``timestamp`` and ``signature`` after asking the
credential to sign the full query string.

The "signed" flag returned alongside the spec tells the node whether
it needs to invoke :func:`~weftlyflow.credentials.types.binance_api.sign_query`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.binance.constants import (
    OP_ACCOUNT_INFO,
    OP_CANCEL_ORDER,
    OP_GET_TICKER_PRICE,
    OP_PLACE_ORDER,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
    SIGNED_OPERATIONS,
)

RequestSpec = tuple[str, str, dict[str, str]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Binance: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def is_signed(operation: str) -> bool:
    """Return True if ``operation`` requires HMAC-SHA256 signing."""
    return operation in SIGNED_OPERATIONS


def _build_account_info(_params: dict[str, Any]) -> RequestSpec:
    return "GET", "/api/v3/account", {}


def _build_get_ticker_price(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, str] = {}
    symbol = str(params.get("symbol") or "").strip().upper()
    if symbol:
        query["symbol"] = symbol
    return "GET", "/api/v3/ticker/price", query


def _build_place_order(params: dict[str, Any]) -> RequestSpec:
    symbol = _required_str(params, "symbol").upper()
    side = str(params.get("side") or "").strip().lower()
    if side not in (SIDE_BUY, SIDE_SELL):
        msg = f"Binance: 'side' must be 'buy' or 'sell' — got {side!r}"
        raise ValueError(msg)
    order_type = str(params.get("order_type") or ORDER_TYPE_LIMIT).strip().lower()
    if order_type not in (ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET):
        msg = f"Binance: 'order_type' must be 'limit' or 'market' — got {order_type!r}"
        raise ValueError(msg)
    query: dict[str, str] = {
        "symbol": symbol,
        "side": side.upper(),
        "type": order_type.upper(),
    }
    quantity = str(params.get("quantity") or "").strip()
    quote_qty = str(params.get("quote_order_qty") or "").strip()
    if order_type == ORDER_TYPE_LIMIT:
        query["price"] = _required_str(params, "price")
        if not quantity:
            msg = "Binance: 'quantity' is required for limit orders"
            raise ValueError(msg)
        query["quantity"] = quantity
        tif = str(params.get("time_in_force") or "GTC").strip().upper()
        query["timeInForce"] = tif
    else:
        if not quantity and not quote_qty:
            msg = "Binance: market orders require 'quantity' or 'quote_order_qty'"
            raise ValueError(msg)
        if quantity:
            query["quantity"] = quantity
        if quote_qty:
            query["quoteOrderQty"] = quote_qty
    client_order_id = str(params.get("client_order_id") or "").strip()
    if client_order_id:
        query["newClientOrderId"] = client_order_id
    return "POST", "/api/v3/order", query


def _build_cancel_order(params: dict[str, Any]) -> RequestSpec:
    symbol = _required_str(params, "symbol").upper()
    order_id = str(params.get("order_id") or "").strip()
    orig_client_id = str(params.get("orig_client_order_id") or "").strip()
    if not order_id and not orig_client_id:
        msg = "Binance: cancel requires 'order_id' or 'orig_client_order_id'"
        raise ValueError(msg)
    query: dict[str, str] = {"symbol": symbol}
    if order_id:
        query["orderId"] = order_id
    if orig_client_id:
        query["origClientOrderId"] = orig_client_id
    return "DELETE", "/api/v3/order", query


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Binance: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_ACCOUNT_INFO: _build_account_info,
    OP_GET_TICKER_PRICE: _build_get_ticker_price,
    OP_PLACE_ORDER: _build_place_order,
    OP_CANCEL_ORDER: _build_cancel_order,
}
