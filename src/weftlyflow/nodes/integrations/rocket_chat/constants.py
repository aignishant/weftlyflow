"""Constants for the Rocket.Chat integration node.

Reference: https://developer.rocket.chat/reference/api/rest-api.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_POST_MESSAGE: Final[str] = "post_message"
OP_UPDATE_MESSAGE: Final[str] = "update_message"
OP_DELETE_MESSAGE: Final[str] = "delete_message"
OP_LIST_CHANNELS: Final[str] = "list_channels"
OP_CREATE_CHANNEL: Final[str] = "create_channel"
OP_GET_USER: Final[str] = "get_user"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_POST_MESSAGE,
    OP_UPDATE_MESSAGE,
    OP_DELETE_MESSAGE,
    OP_LIST_CHANNELS,
    OP_CREATE_CHANNEL,
    OP_GET_USER,
)
