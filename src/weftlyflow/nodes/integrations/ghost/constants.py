"""Constants for the Ghost Admin integration node.

Reference: https://ghost.org/docs/admin-api/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
ADMIN_API_BASE: Final[str] = "/ghost/api/admin"

OP_LIST_POSTS: Final[str] = "list_posts"
OP_GET_POST: Final[str] = "get_post"
OP_CREATE_POST: Final[str] = "create_post"
OP_UPDATE_POST: Final[str] = "update_post"
OP_DELETE_POST: Final[str] = "delete_post"
OP_LIST_MEMBERS: Final[str] = "list_members"
OP_CREATE_MEMBER: Final[str] = "create_member"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_POSTS,
    OP_GET_POST,
    OP_CREATE_POST,
    OP_UPDATE_POST,
    OP_DELETE_POST,
    OP_LIST_MEMBERS,
    OP_CREATE_MEMBER,
)
