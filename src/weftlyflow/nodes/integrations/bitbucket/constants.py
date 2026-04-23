"""Constants for the Bitbucket Cloud integration node.

Reference: https://developer.atlassian.com/cloud/bitbucket/rest/intro/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_REPOSITORIES: Final[str] = "list_repositories"
OP_GET_REPOSITORY: Final[str] = "get_repository"
OP_LIST_PULL_REQUESTS: Final[str] = "list_pull_requests"
OP_GET_PULL_REQUEST: Final[str] = "get_pull_request"
OP_CREATE_PULL_REQUEST: Final[str] = "create_pull_request"
OP_LIST_ISSUES: Final[str] = "list_issues"
OP_CREATE_ISSUE: Final[str] = "create_issue"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_REPOSITORIES,
    OP_GET_REPOSITORY,
    OP_LIST_PULL_REQUESTS,
    OP_GET_PULL_REQUEST,
    OP_CREATE_PULL_REQUEST,
    OP_LIST_ISSUES,
    OP_CREATE_ISSUE,
)
