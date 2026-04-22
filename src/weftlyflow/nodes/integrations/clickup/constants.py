"""Constants for the ClickUp v2 integration node.

Reference: https://clickup.com/api.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.clickup.com"
API_VERSION_PREFIX: Final[str] = "/api/v2"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_CREATE_TASK: Final[str] = "create_task"
OP_GET_TASK: Final[str] = "get_task"
OP_UPDATE_TASK: Final[str] = "update_task"
OP_DELETE_TASK: Final[str] = "delete_task"
OP_LIST_TASKS: Final[str] = "list_tasks"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CREATE_TASK,
    OP_GET_TASK,
    OP_UPDATE_TASK,
    OP_DELETE_TASK,
    OP_LIST_TASKS,
)
