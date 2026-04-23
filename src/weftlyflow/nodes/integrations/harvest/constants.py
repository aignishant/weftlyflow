"""Constants for the Harvest integration node.

Reference: https://help.getharvest.com/api-v2/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.harvestapp.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 15.0

OP_LIST_TIME_ENTRIES: Final[str] = "list_time_entries"
OP_CREATE_TIME_ENTRY: Final[str] = "create_time_entry"
OP_LIST_PROJECTS: Final[str] = "list_projects"
OP_GET_USER_ME: Final[str] = "get_user_me"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_TIME_ENTRIES,
    OP_CREATE_TIME_ENTRY,
    OP_LIST_PROJECTS,
    OP_GET_USER_ME,
)
