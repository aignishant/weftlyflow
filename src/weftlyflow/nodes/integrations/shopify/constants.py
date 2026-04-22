"""Constants for the Shopify Admin API integration node.

Reference: https://shopify.dev/docs/api/admin-rest.
"""

from __future__ import annotations

from typing import Final

DEFAULT_API_VERSION: Final[str] = "2024-07"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_PRODUCTS: Final[str] = "list_products"
OP_GET_PRODUCT: Final[str] = "get_product"
OP_CREATE_PRODUCT: Final[str] = "create_product"
OP_UPDATE_PRODUCT: Final[str] = "update_product"
OP_LIST_ORDERS: Final[str] = "list_orders"
OP_GET_ORDER: Final[str] = "get_order"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_PRODUCTS,
    OP_GET_PRODUCT,
    OP_CREATE_PRODUCT,
    OP_UPDATE_PRODUCT,
    OP_LIST_ORDERS,
    OP_GET_ORDER,
)

DEFAULT_LIST_LIMIT: Final[int] = 50
MAX_LIST_LIMIT: Final[int] = 250
