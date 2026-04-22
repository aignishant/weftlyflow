"""Constants for the Monday.com GraphQL integration node.

Reference: https://developer.monday.com/api-reference/docs.
"""

from __future__ import annotations

from typing import Final

API_URL: Final[str] = "https://api.monday.com/v2"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_GET_BOARDS: Final[str] = "get_boards"
OP_GET_BOARD: Final[str] = "get_board"
OP_GET_ITEMS: Final[str] = "get_items"
OP_CREATE_ITEM: Final[str] = "create_item"
OP_CHANGE_COLUMN_VALUES: Final[str] = "change_column_values"
OP_CREATE_UPDATE: Final[str] = "create_update"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_BOARDS,
    OP_GET_BOARD,
    OP_GET_ITEMS,
    OP_CREATE_ITEM,
    OP_CHANGE_COLUMN_VALUES,
    OP_CREATE_UPDATE,
)

DEFAULT_PAGE_LIMIT: Final[int] = 25
MAX_PAGE_LIMIT: Final[int] = 500
