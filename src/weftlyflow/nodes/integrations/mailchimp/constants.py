"""Constants for the Mailchimp Marketing v3 integration node.

Reference: https://mailchimp.com/developer/marketing/api/.
"""

from __future__ import annotations

from typing import Final

API_VERSION_PREFIX: Final[str] = "/3.0"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_LISTS: Final[str] = "list_lists"
OP_GET_LIST: Final[str] = "get_list"
OP_ADD_MEMBER: Final[str] = "add_member"
OP_UPDATE_MEMBER: Final[str] = "update_member"
OP_GET_MEMBER: Final[str] = "get_member"
OP_TAG_MEMBER: Final[str] = "tag_member"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_LISTS,
    OP_GET_LIST,
    OP_ADD_MEMBER,
    OP_UPDATE_MEMBER,
    OP_GET_MEMBER,
    OP_TAG_MEMBER,
)

DEFAULT_LIST_LIMIT: Final[int] = 10
MAX_LIST_LIMIT: Final[int] = 1000

MEMBER_STATUSES: Final[frozenset[str]] = frozenset(
    {"subscribed", "unsubscribed", "cleaned", "pending", "transactional"},
)
