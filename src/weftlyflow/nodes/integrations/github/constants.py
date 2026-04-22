"""Constants for the GitHub integration node.

Reference: https://docs.github.com/en/rest.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
ACCEPT_HEADER: Final[str] = "application/vnd.github+json"
API_VERSION_HEADER: Final[str] = "2022-11-28"

OP_CREATE_ISSUE: Final[str] = "create_issue"
OP_LIST_ISSUES: Final[str] = "list_issues"
OP_GET_REPO: Final[str] = "get_repo"
OP_CREATE_COMMENT: Final[str] = "create_comment"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CREATE_ISSUE,
    OP_LIST_ISSUES,
    OP_GET_REPO,
    OP_CREATE_COMMENT,
)

DEFAULT_LIST_PER_PAGE: Final[int] = 30
MAX_LIST_PER_PAGE: Final[int] = 100

ISSUE_STATE_OPEN: Final[str] = "open"
ISSUE_STATE_CLOSED: Final[str] = "closed"
ISSUE_STATE_ALL: Final[str] = "all"
VALID_ISSUE_STATES: Final[frozenset[str]] = frozenset(
    {ISSUE_STATE_OPEN, ISSUE_STATE_CLOSED, ISSUE_STATE_ALL},
)
