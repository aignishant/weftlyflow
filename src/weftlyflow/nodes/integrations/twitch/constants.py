"""Constants for the Twitch Helix integration node.

Reference: https://dev.twitch.tv/docs/api/reference/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.twitch.tv/helix"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_GET_USERS: Final[str] = "get_users"
OP_GET_CHANNEL: Final[str] = "get_channel"
OP_GET_STREAMS: Final[str] = "get_streams"
OP_GET_VIDEOS: Final[str] = "get_videos"
OP_GET_FOLLOWERS: Final[str] = "get_followers"
OP_SEARCH_CHANNELS: Final[str] = "search_channels"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_USERS,
    OP_GET_CHANNEL,
    OP_GET_STREAMS,
    OP_GET_VIDEOS,
    OP_GET_FOLLOWERS,
    OP_SEARCH_CHANNELS,
)

DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100
