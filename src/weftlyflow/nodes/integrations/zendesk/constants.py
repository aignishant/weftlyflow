"""Constants for the Zendesk Support REST integration node.

Reference: https://developer.zendesk.com/api-reference/ticketing/introduction/.
"""

from __future__ import annotations

from typing import Final

API_VERSION_PREFIX: Final[str] = "/api/v2"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_GET_TICKET: Final[str] = "get_ticket"
OP_CREATE_TICKET: Final[str] = "create_ticket"
OP_UPDATE_TICKET: Final[str] = "update_ticket"
OP_LIST_TICKETS: Final[str] = "list_tickets"
OP_ADD_COMMENT: Final[str] = "add_comment"
OP_SEARCH: Final[str] = "search"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_TICKET,
    OP_CREATE_TICKET,
    OP_UPDATE_TICKET,
    OP_LIST_TICKETS,
    OP_ADD_COMMENT,
    OP_SEARCH,
)

DEFAULT_LIST_LIMIT: Final[int] = 25
MAX_LIST_LIMIT: Final[int] = 100
