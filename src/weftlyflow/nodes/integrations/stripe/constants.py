"""Constants for the Stripe integration node.

Reference: https://stripe.com/docs/api.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.stripe.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_CREATE_CUSTOMER: Final[str] = "create_customer"
OP_LIST_CUSTOMERS: Final[str] = "list_customers"
OP_CREATE_PAYMENT_INTENT: Final[str] = "create_payment_intent"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CREATE_CUSTOMER,
    OP_LIST_CUSTOMERS,
    OP_CREATE_PAYMENT_INTENT,
)

DEFAULT_LIST_LIMIT: Final[int] = 10
MAX_LIST_LIMIT: Final[int] = 100
