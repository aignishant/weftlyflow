"""Constants for the Discord integration node.

Reference: https://discord.com/developers/docs/reference.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://discord.com"
API_VERSION_PREFIX: Final[str] = "/api/v10"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEND_MESSAGE: Final[str] = "send_message"
OP_GET_CHANNEL: Final[str] = "get_channel"
OP_EDIT_MESSAGE: Final[str] = "edit_message"
OP_DELETE_MESSAGE: Final[str] = "delete_message"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SEND_MESSAGE,
    OP_GET_CHANNEL,
    OP_EDIT_MESSAGE,
    OP_DELETE_MESSAGE,
)

MAX_CONTENT_LENGTH: Final[int] = 2000
