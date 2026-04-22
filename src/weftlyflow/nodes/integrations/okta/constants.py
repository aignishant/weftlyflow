"""Constants for the Okta v1 integration node.

Reference: https://developer.okta.com/docs/reference/core-okta-api/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_USERS: Final[str] = "list_users"
OP_GET_USER: Final[str] = "get_user"
OP_CREATE_USER: Final[str] = "create_user"
OP_UPDATE_USER: Final[str] = "update_user"
OP_DEACTIVATE_USER: Final[str] = "deactivate_user"
OP_LIST_GROUPS: Final[str] = "list_groups"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_USERS,
    OP_GET_USER,
    OP_CREATE_USER,
    OP_UPDATE_USER,
    OP_DEACTIVATE_USER,
    OP_LIST_GROUPS,
)

DEFAULT_LIMIT: Final[int] = 50
MAX_LIMIT: Final[int] = 200

USER_PROFILE_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "firstName",
    "lastName",
    "email",
    "login",
)

USER_UPDATE_PROFILE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "firstName",
        "lastName",
        "email",
        "secondEmail",
        "login",
        "mobilePhone",
        "displayName",
        "nickName",
        "title",
        "department",
        "organization",
    },
)
