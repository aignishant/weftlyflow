"""Constants for the Mattermost v4 integration node.

Reference: https://api.mattermost.com/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_POST_MESSAGE: Final[str] = "post_message"
OP_UPDATE_POST: Final[str] = "update_post"
OP_DELETE_POST: Final[str] = "delete_post"
OP_GET_CHANNEL: Final[str] = "get_channel"
OP_LIST_CHANNELS_FOR_USER: Final[str] = "list_channels_for_user"
OP_GET_USER_BY_USERNAME: Final[str] = "get_user_by_username"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_POST_MESSAGE,
    OP_UPDATE_POST,
    OP_DELETE_POST,
    OP_GET_CHANNEL,
    OP_LIST_CHANNELS_FOR_USER,
    OP_GET_USER_BY_USERNAME,
)
