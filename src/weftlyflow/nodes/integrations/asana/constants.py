"""Constants for the Asana integration node.

Reference: https://developers.asana.com/reference.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://app.asana.com/api/1.0"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
ENABLE_HEADER: Final[str] = "Asana-Enable"

OP_LIST_TASKS: Final[str] = "list_tasks"
OP_GET_TASK: Final[str] = "get_task"
OP_CREATE_TASK: Final[str] = "create_task"
OP_UPDATE_TASK: Final[str] = "update_task"
OP_DELETE_TASK: Final[str] = "delete_task"
OP_ADD_COMMENT: Final[str] = "add_comment"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_TASKS,
    OP_GET_TASK,
    OP_CREATE_TASK,
    OP_UPDATE_TASK,
    OP_DELETE_TASK,
    OP_ADD_COMMENT,
)

DEFAULT_PAGE_SIZE: Final[int] = 50
MAX_PAGE_SIZE: Final[int] = 100
