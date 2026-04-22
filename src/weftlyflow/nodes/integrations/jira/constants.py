"""Constants for the Jira Cloud v3 integration node.

Reference: https://developer.atlassian.com/cloud/jira/platform/rest/v3/.
"""

from __future__ import annotations

from typing import Final

API_VERSION_PREFIX: Final[str] = "/rest/api/3"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_GET_ISSUE: Final[str] = "get_issue"
OP_CREATE_ISSUE: Final[str] = "create_issue"
OP_UPDATE_ISSUE: Final[str] = "update_issue"
OP_DELETE_ISSUE: Final[str] = "delete_issue"
OP_SEARCH_ISSUES: Final[str] = "search_issues"
OP_ADD_COMMENT: Final[str] = "add_comment"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_ISSUE,
    OP_CREATE_ISSUE,
    OP_UPDATE_ISSUE,
    OP_DELETE_ISSUE,
    OP_SEARCH_ISSUES,
    OP_ADD_COMMENT,
)

DEFAULT_SEARCH_LIMIT: Final[int] = 50
MAX_SEARCH_LIMIT: Final[int] = 100
