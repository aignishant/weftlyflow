"""Constants for the Trello integration node.

Reference: https://developer.atlassian.com/cloud/trello/rest/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.trello.com"
API_VERSION_PREFIX: Final[str] = "/1"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_GET_BOARD: Final[str] = "get_board"
OP_LIST_CARDS: Final[str] = "list_cards"
OP_GET_CARD: Final[str] = "get_card"
OP_CREATE_CARD: Final[str] = "create_card"
OP_UPDATE_CARD: Final[str] = "update_card"
OP_DELETE_CARD: Final[str] = "delete_card"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_BOARD,
    OP_LIST_CARDS,
    OP_GET_CARD,
    OP_CREATE_CARD,
    OP_UPDATE_CARD,
    OP_DELETE_CARD,
)
