"""Constants for the Plaid integration node.

Reference: https://plaid.com/docs/api/.
"""

from __future__ import annotations

from typing import Final

HOSTS: Final[dict[str, str]] = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}
DEFAULT_ENVIRONMENT: Final[str] = "sandbox"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 20.0

OP_LINK_TOKEN_CREATE: Final[str] = "link_token_create"
OP_ITEM_GET: Final[str] = "item_get"
OP_ACCOUNTS_GET: Final[str] = "accounts_get"
OP_TRANSACTIONS_SYNC: Final[str] = "transactions_sync"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LINK_TOKEN_CREATE,
    OP_ITEM_GET,
    OP_ACCOUNTS_GET,
    OP_TRANSACTIONS_SYNC,
)
