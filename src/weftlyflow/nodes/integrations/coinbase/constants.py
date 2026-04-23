"""Constants for the Coinbase Exchange integration node.

Reference: https://docs.cdp.coinbase.com/exchange/docs/rest-api-overview.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.exchange.coinbase.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 20.0

OP_LIST_ACCOUNTS: Final[str] = "list_accounts"
OP_GET_PRODUCT_TICKER: Final[str] = "get_product_ticker"
OP_PLACE_ORDER: Final[str] = "place_order"
OP_CANCEL_ORDER: Final[str] = "cancel_order"

SIDE_BUY: Final[str] = "buy"
SIDE_SELL: Final[str] = "sell"
ORDER_TYPE_LIMIT: Final[str] = "limit"
ORDER_TYPE_MARKET: Final[str] = "market"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_ACCOUNTS,
    OP_GET_PRODUCT_TICKER,
    OP_PLACE_ORDER,
    OP_CANCEL_ORDER,
)
