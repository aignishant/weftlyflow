"""Constants for the QuickBooks Online integration node.

Reference: https://developer.intuit.com/app/developer/qbo/docs/api/accounting.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0

OP_QUERY: Final[str] = "query"
OP_GET_INVOICE: Final[str] = "get_invoice"
OP_CREATE_INVOICE: Final[str] = "create_invoice"
OP_GET_CUSTOMER: Final[str] = "get_customer"
OP_CREATE_CUSTOMER: Final[str] = "create_customer"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_QUERY,
    OP_GET_INVOICE,
    OP_CREATE_INVOICE,
    OP_GET_CUSTOMER,
    OP_CREATE_CUSTOMER,
)
