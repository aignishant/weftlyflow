"""Constants for the PayPal REST integration node.

Reference: https://developer.paypal.com/api/rest/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
REQUEST_ID_HEADER: Final[str] = "PayPal-Request-Id"

OP_CREATE_ORDER: Final[str] = "create_order"
OP_GET_ORDER: Final[str] = "get_order"
OP_CAPTURE_ORDER: Final[str] = "capture_order"
OP_REFUND_CAPTURE: Final[str] = "refund_capture"
OP_LIST_INVOICES: Final[str] = "list_invoices"
OP_GET_INVOICE: Final[str] = "get_invoice"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CREATE_ORDER,
    OP_GET_ORDER,
    OP_CAPTURE_ORDER,
    OP_REFUND_CAPTURE,
    OP_LIST_INVOICES,
    OP_GET_INVOICE,
)
