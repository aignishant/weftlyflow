"""Constants for the Telegram Bot API integration node.

Reference: https://core.telegram.org/bots/api.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.telegram.org"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEND_MESSAGE: Final[str] = "send_message"
OP_SEND_PHOTO: Final[str] = "send_photo"
OP_EDIT_MESSAGE_TEXT: Final[str] = "edit_message_text"
OP_DELETE_MESSAGE: Final[str] = "delete_message"
OP_GET_UPDATES: Final[str] = "get_updates"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SEND_MESSAGE,
    OP_SEND_PHOTO,
    OP_EDIT_MESSAGE_TEXT,
    OP_DELETE_MESSAGE,
    OP_GET_UPDATES,
)

MAX_MESSAGE_LENGTH: Final[int] = 4096
MAX_CAPTION_LENGTH: Final[int] = 1024
