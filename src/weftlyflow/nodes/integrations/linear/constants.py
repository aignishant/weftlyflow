"""Constants for the Linear GraphQL integration node.

Reference: https://developers.linear.app/docs/graphql/working-with-the-graphql-api/.
"""

from __future__ import annotations

from typing import Final

API_URL: Final[str] = "https://api.linear.app/graphql"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_ISSUES: Final[str] = "list_issues"
OP_GET_ISSUE: Final[str] = "get_issue"
OP_CREATE_ISSUE: Final[str] = "create_issue"
OP_UPDATE_ISSUE: Final[str] = "update_issue"
OP_LIST_TEAMS: Final[str] = "list_teams"
OP_LIST_PROJECTS: Final[str] = "list_projects"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_ISSUES,
    OP_GET_ISSUE,
    OP_CREATE_ISSUE,
    OP_UPDATE_ISSUE,
    OP_LIST_TEAMS,
    OP_LIST_PROJECTS,
)

DEFAULT_PAGE_SIZE: Final[int] = 50
MAX_PAGE_SIZE: Final[int] = 250

ISSUE_UPDATE_INPUT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "title",
        "description",
        "priority",
        "stateId",
        "assigneeId",
        "teamId",
        "projectId",
        "labelIds",
        "dueDate",
        "estimate",
    },
)
