"""Constants for the Binance Spot integration node.

Reference: https://developers.binance.com/docs/binance-spot-api-docs/rest-api.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 20.0

OP_ACCOUNT_INFO: Final[str] = "account_info"
OP_GET_TICKER_PRICE: Final[str] = "get_ticker_price"
OP_PLACE_ORDER: Final[str] = "place_order"
OP_CANCEL_ORDER: Final[str] = "cancel_order"

SIDE_BUY: Final[str] = "buy"
SIDE_SELL: Final[str] = "sell"
ORDER_TYPE_LIMIT: Final[str] = "limit"
ORDER_TYPE_MARKET: Final[str] = "market"
TIME_IN_FORCE_GTC: Final[str] = "gtc"

SIGNED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_ACCOUNT_INFO,
    OP_PLACE_ORDER,
    OP_CANCEL_ORDER,
)

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_ACCOUNT_INFO,
    OP_GET_TICKER_PRICE,
    OP_PLACE_ORDER,
    OP_CANCEL_ORDER,
)
