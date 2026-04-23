"""Per-operation request builders for the Alpaca Markets node.

Each builder returns ``(http_method, path, body)``. Paths are relative
to the host selected from the credential's ``environment`` field.
Auth is injected by the credential via the paired ``APCA-API-*``
headers, so builders deal only with URL shape and body content.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.alpaca.constants import (
    OP_GET_ACCOUNT,
    OP_GET_CLOCK,
    OP_LIST_POSITIONS,
    OP_PLACE_ORDER,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
    TIF_DAY,
    TIF_FOK,
    TIF_GTC,
    TIF_IOC,
)

RequestSpec = tuple[str, str, dict[str, Any] | None]

_VALID_TIF: frozenset[str] = frozenset({TIF_DAY, TIF_GTC, TIF_IOC, TIF_FOK})


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Alpaca: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_account(_params: dict[str, Any]) -> RequestSpec:
    return "GET", "/v2/account", None


def _build_list_positions(_params: dict[str, Any]) -> RequestSpec:
    return "GET", "/v2/positions", None


def _build_get_clock(_params: dict[str, Any]) -> RequestSpec:
    return "GET", "/v2/clock", None


def _build_place_order(params: dict[str, Any]) -> RequestSpec:
    symbol = _required_str(params, "symbol").upper()
    side = str(params.get("side") or "").strip().lower()
    if side not in (SIDE_BUY, SIDE_SELL):
        msg = f"Alpaca: 'side' must be 'buy' or 'sell' — got {side!r}"
        raise ValueError(msg)
    order_type = str(params.get("order_type") or ORDER_TYPE_MARKET).strip().lower()
    if order_type not in (ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT):
        msg = f"Alpaca: 'order_type' must be 'market' or 'limit' — got {order_type!r}"
        raise ValueError(msg)
    tif = str(params.get("time_in_force") or TIF_DAY).strip().lower()
    if tif not in _VALID_TIF:
        msg = f"Alpaca: 'time_in_force' must be one of day/gtc/ioc/fok — got {tif!r}"
        raise ValueError(msg)
    qty = str(params.get("qty") or "").strip()
    notional = str(params.get("notional") or "").strip()
    if not qty and not notional:
        msg = "Alpaca: orders require 'qty' or 'notional'"
        raise ValueError(msg)
    body: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "time_in_force": tif,
    }
    if qty:
        body["qty"] = qty
    if notional:
        body["notional"] = notional
    if order_type == ORDER_TYPE_LIMIT:
        body["limit_price"] = _required_str(params, "limit_price")
    client_order_id = str(params.get("client_order_id") or "").strip()
    if client_order_id:
        body["client_order_id"] = client_order_id
    return "POST", "/v2/orders", body


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Alpaca: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_ACCOUNT: _build_get_account,
    OP_LIST_POSITIONS: _build_list_positions,
    OP_PLACE_ORDER: _build_place_order,
    OP_GET_CLOCK: _build_get_clock,
}
