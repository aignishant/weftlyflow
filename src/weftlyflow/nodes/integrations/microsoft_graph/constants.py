"""Constants for the Microsoft Graph integration node.

Reference: https://learn.microsoft.com/en-us/graph/api/overview.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://graph.microsoft.com/v1.0"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
CONSISTENCY_LEVEL_HEADER: Final[str] = "ConsistencyLevel"
CONSISTENCY_LEVEL_EVENTUAL: Final[str] = "eventual"

OP_LIST_USERS: Final[str] = "list_users"
OP_GET_USER: Final[str] = "get_user"
OP_LIST_MESSAGES: Final[str] = "list_messages"
OP_SEND_MAIL: Final[str] = "send_mail"
OP_LIST_EVENTS: Final[str] = "list_events"
OP_CREATE_EVENT: Final[str] = "create_event"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_USERS,
    OP_GET_USER,
    OP_LIST_MESSAGES,
    OP_SEND_MAIL,
    OP_LIST_EVENTS,
    OP_CREATE_EVENT,
)

DEFAULT_PAGE_SIZE: Final[int] = 50
MAX_PAGE_SIZE: Final[int] = 999
