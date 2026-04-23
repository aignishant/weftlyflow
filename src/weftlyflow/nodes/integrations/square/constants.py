"""Constants for the Square integration node.

Reference: https://developer.squareup.com/reference/square.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0
VERSION_HEADER: Final[str] = "Square-Version"

OP_LIST_CUSTOMERS: Final[str] = "list_customers"
OP_GET_CUSTOMER: Final[str] = "get_customer"
OP_CREATE_CUSTOMER: Final[str] = "create_customer"
OP_LIST_PAYMENTS: Final[str] = "list_payments"
OP_CREATE_PAYMENT: Final[str] = "create_payment"
OP_SEARCH_ORDERS: Final[str] = "search_orders"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_CUSTOMERS,
    OP_GET_CUSTOMER,
    OP_CREATE_CUSTOMER,
    OP_LIST_PAYMENTS,
    OP_CREATE_PAYMENT,
    OP_SEARCH_ORDERS,
)
