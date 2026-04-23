"""Per-operation request builders for the Coinbase Exchange node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to :data:`API_BASE_URL`. The HMAC signature is computed by
the credential from the final URL + body, so builders do not need to
worry about auth.

Coinbase's ``place_order`` endpoint accepts **either** a limit order
(``price`` + ``size``) or a market order (``size`` **or** ``funds``);
the builder forwards whichever combination the caller supplied and
validates that at least one sizing field is present.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.coinbase.constants import (
    OP_CANCEL_ORDER,
    OP_GET_PRODUCT_TICKER,
    OP_LIST_ACCOUNTS,
    OP_PLACE_ORDER,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Coinbase: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_accounts(_params: dict[str, Any]) -> RequestSpec:
    return "GET", "/accounts", None, {}


def _build_get_product_ticker(params: dict[str, Any]) -> RequestSpec:
    product_id = _required_str(params, "product_id")
    return "GET", f"/products/{product_id}/ticker", None, {}


def _build_place_order(params: dict[str, Any]) -> RequestSpec:
    side = str(params.get("side") or "").strip().lower()
    if side not in (SIDE_BUY, SIDE_SELL):
        msg = f"Coinbase: 'side' must be 'buy' or 'sell' — got {side!r}"
        raise ValueError(msg)
    order_type = str(params.get("order_type") or ORDER_TYPE_LIMIT).strip().lower()
    if order_type not in (ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET):
        msg = f"Coinbase: 'order_type' must be 'limit' or 'market' — got {order_type!r}"
        raise ValueError(msg)
    body: dict[str, Any] = {
        "product_id": _required_str(params, "product_id"),
        "side": side,
        "type": order_type,
    }
    client_oid = str(params.get("client_oid") or "").strip()
    if client_oid:
        body["client_oid"] = client_oid
    if order_type == ORDER_TYPE_LIMIT:
        body["price"] = _required_str(params, "price")
        body["size"] = _required_str(params, "size")
        tif = str(params.get("time_in_force") or "").strip()
        if tif:
            body["time_in_force"] = tif
    else:
        size = str(params.get("size") or "").strip()
        funds = str(params.get("funds") or "").strip()
        if not size and not funds:
            msg = "Coinbase: market orders require either 'size' or 'funds'"
            raise ValueError(msg)
        if size:
            body["size"] = size
        if funds:
            body["funds"] = funds
    return "POST", "/orders", body, {}


def _build_cancel_order(params: dict[str, Any]) -> RequestSpec:
    order_id = _required_str(params, "order_id")
    return "DELETE", f"/orders/{order_id}", None, {}


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Coinbase: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_ACCOUNTS: _build_list_accounts,
    OP_GET_PRODUCT_TICKER: _build_get_product_ticker,
    OP_PLACE_ORDER: _build_place_order,
    OP_CANCEL_ORDER: _build_cancel_order,
}
