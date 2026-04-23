"""Constants for the Box integration node.

Reference: https://developer.box.com/reference/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.box.com/2.0"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0
AS_USER_HEADER: Final[str] = "As-User"

OP_LIST_FOLDER: Final[str] = "list_folder"
OP_GET_FILE: Final[str] = "get_file"
OP_DELETE_FILE: Final[str] = "delete_file"
OP_CREATE_FOLDER: Final[str] = "create_folder"
OP_COPY_FILE: Final[str] = "copy_file"
OP_SEARCH: Final[str] = "search"
OP_LIST_USERS: Final[str] = "list_users"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_FOLDER,
    OP_GET_FILE,
    OP_DELETE_FILE,
    OP_CREATE_FOLDER,
    OP_COPY_FILE,
    OP_SEARCH,
    OP_LIST_USERS,
)

DEFAULT_PAGE_SIZE: Final[int] = 100
MAX_PAGE_SIZE: Final[int] = 1_000
