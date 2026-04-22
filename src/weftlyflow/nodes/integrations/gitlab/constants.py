"""Constants for the GitLab v4 integration node.

Reference: https://docs.gitlab.com/ee/api/rest/.
"""

from __future__ import annotations

from typing import Final

API_VERSION_PREFIX: Final[str] = "/api/v4"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_GET_ISSUE: Final[str] = "get_issue"
OP_CREATE_ISSUE: Final[str] = "create_issue"
OP_UPDATE_ISSUE: Final[str] = "update_issue"
OP_LIST_ISSUES: Final[str] = "list_issues"
OP_ADD_COMMENT: Final[str] = "add_comment"
OP_LIST_MERGE_REQUESTS: Final[str] = "list_merge_requests"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_ISSUE,
    OP_CREATE_ISSUE,
    OP_UPDATE_ISSUE,
    OP_LIST_ISSUES,
    OP_ADD_COMMENT,
    OP_LIST_MERGE_REQUESTS,
)

DEFAULT_LIST_LIMIT: Final[int] = 20
MAX_LIST_LIMIT: Final[int] = 100
