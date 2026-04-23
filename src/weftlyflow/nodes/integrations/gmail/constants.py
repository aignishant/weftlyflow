"""Constants for the Gmail integration node.

Reference: https://developers.google.com/gmail/api/reference/rest.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
GMAIL_API_BASE: Final[str] = "https://gmail.googleapis.com"
GMAIL_API_PREFIX: Final[str] = "/gmail/v1/users/me"

OP_SEND_MESSAGE: Final[str] = "send_message"
OP_LIST_MESSAGES: Final[str] = "list_messages"
OP_GET_MESSAGE: Final[str] = "get_message"
OP_TRASH_MESSAGE: Final[str] = "trash_message"
OP_ADD_LABEL: Final[str] = "add_label"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SEND_MESSAGE,
    OP_LIST_MESSAGES,
    OP_GET_MESSAGE,
    OP_TRASH_MESSAGE,
    OP_ADD_LABEL,
)
