"""Constants for the Reddit integration node.

Reference: https://www.reddit.com/dev/api/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://oauth.reddit.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 20.0

OP_GET_ME: Final[str] = "get_me"
OP_SUBMIT_POST: Final[str] = "submit_post"
OP_GET_SUBREDDIT: Final[str] = "get_subreddit"
OP_LIST_HOT: Final[str] = "list_hot"

KIND_LINK: Final[str] = "link"
KIND_SELF: Final[str] = "self"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_ME,
    OP_SUBMIT_POST,
    OP_GET_SUBREDDIT,
    OP_LIST_HOT,
)
