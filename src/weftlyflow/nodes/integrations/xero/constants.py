"""Constants for the Xero integration node.

Reference: https://developer.xero.com/documentation/api/accounting/overview.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.xero.com/api.xro/2.0"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0
MAX_PAGE_SIZE: Final[int] = 100

OP_LIST_INVOICES: Final[str] = "list_invoices"
OP_GET_INVOICE: Final[str] = "get_invoice"
OP_CREATE_INVOICE: Final[str] = "create_invoice"
OP_UPDATE_INVOICE: Final[str] = "update_invoice"
OP_LIST_CONTACTS: Final[str] = "list_contacts"
OP_LIST_ACCOUNTS: Final[str] = "list_accounts"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_INVOICES,
    OP_GET_INVOICE,
    OP_CREATE_INVOICE,
    OP_UPDATE_INVOICE,
    OP_LIST_CONTACTS,
    OP_LIST_ACCOUNTS,
)
