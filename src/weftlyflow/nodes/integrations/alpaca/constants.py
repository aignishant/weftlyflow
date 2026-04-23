"""Constants for the Alpaca Markets integration node.

Reference: https://docs.alpaca.markets/reference/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 20.0

OP_GET_ACCOUNT: Final[str] = "get_account"
OP_LIST_POSITIONS: Final[str] = "list_positions"
OP_PLACE_ORDER: Final[str] = "place_order"
OP_GET_CLOCK: Final[str] = "get_clock"

SIDE_BUY: Final[str] = "buy"
SIDE_SELL: Final[str] = "sell"
ORDER_TYPE_MARKET: Final[str] = "market"
ORDER_TYPE_LIMIT: Final[str] = "limit"
TIF_DAY: Final[str] = "day"
TIF_GTC: Final[str] = "gtc"
TIF_IOC: Final[str] = "ioc"
TIF_FOK: Final[str] = "fok"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_ACCOUNT,
    OP_LIST_POSITIONS,
    OP_PLACE_ORDER,
    OP_GET_CLOCK,
)
