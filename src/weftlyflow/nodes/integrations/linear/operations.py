"""Per-operation GraphQL builders for the Linear node.

Each builder returns ``(operation_name, query, variables)`` — the node
layer POSTs ``{"query": query, "variables": variables, "operationName":
operation_name}`` to ``https://api.linear.app/graphql``.

Linear's GraphQL surface is a single endpoint; the diversity sits in
the body shape. Mutations use ``*Input`` type names (``IssueCreateInput``,
``IssueUpdateInput``) and return ``{ success, <entity>: {...} }``
payloads; queries return cursor-paginated connections with
``pageInfo { hasNextPage endCursor }``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.linear.constants import (
    DEFAULT_PAGE_SIZE,
    ISSUE_UPDATE_INPUT_FIELDS,
    MAX_PAGE_SIZE,
    OP_CREATE_ISSUE,
    OP_GET_ISSUE,
    OP_LIST_ISSUES,
    OP_LIST_PROJECTS,
    OP_LIST_TEAMS,
    OP_UPDATE_ISSUE,
)

GraphQLRequest = tuple[str, str, dict[str, Any]]

_LIST_ISSUES_QUERY = """
query ListIssues($first: Int!, $after: String, $filter: IssueFilter) {
  issues(first: $first, after: $after, filter: $filter) {
    nodes {
      id
      identifier
      title
      priority
      state { id name }
      team { id key name }
      assignee { id name }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

_GET_ISSUE_QUERY = """
query GetIssue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    description
    priority
    state { id name type }
    team { id key name }
    assignee { id name email }
    project { id name }
    labels { nodes { id name color } }
  }
}
""".strip()

_CREATE_ISSUE_QUERY = """
mutation CreateIssue($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title url }
  }
}
""".strip()

_UPDATE_ISSUE_QUERY = """
mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id identifier title }
  }
}
""".strip()

_LIST_TEAMS_QUERY = """
query ListTeams($first: Int!, $after: String) {
  teams(first: $first, after: $after) {
    nodes { id key name description }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

_LIST_PROJECTS_QUERY = """
query ListProjects($first: Int!, $after: String) {
  projects(first: $first, after: $after) {
    nodes { id name state startDate targetDate }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()


def build_request(operation: str, params: dict[str, Any]) -> GraphQLRequest:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Linear: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_issues(params: dict[str, Any]) -> GraphQLRequest:
    variables: dict[str, Any] = {"first": _coerce_page_size(params.get("first"))}
    after = str(params.get("after") or "").strip()
    if after:
        variables["after"] = after
    filter_obj = params.get("filter")
    if filter_obj not in (None, "", {}):
        if not isinstance(filter_obj, dict):
            msg = "Linear: 'filter' must be a JSON object"
            raise ValueError(msg)
        variables["filter"] = dict(filter_obj)
    return "ListIssues", _LIST_ISSUES_QUERY, variables


def _build_get_issue(params: dict[str, Any]) -> GraphQLRequest:
    issue_id = _required(params, "issue_id")
    return "GetIssue", _GET_ISSUE_QUERY, {"id": issue_id}


def _build_create_issue(params: dict[str, Any]) -> GraphQLRequest:
    team_id = _required(params, "team_id")
    title = _required(params, "title")
    input_payload: dict[str, Any] = {"teamId": team_id, "title": title}
    description = str(params.get("description") or "").strip()
    if description:
        input_payload["description"] = description
    extra = params.get("extra")
    if extra not in (None, "", {}):
        if not isinstance(extra, dict):
            msg = "Linear: 'extra' must be a JSON object"
            raise ValueError(msg)
        unknown = [k for k in extra if k not in ISSUE_UPDATE_INPUT_FIELDS]
        if unknown:
            msg = f"Linear: unknown issue input field(s) {unknown!r}"
            raise ValueError(msg)
        input_payload.update(extra)
    return "CreateIssue", _CREATE_ISSUE_QUERY, {"input": input_payload}


def _build_update_issue(params: dict[str, Any]) -> GraphQLRequest:
    issue_id = _required(params, "issue_id")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Linear: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    unknown = [k for k in fields if k not in ISSUE_UPDATE_INPUT_FIELDS]
    if unknown:
        msg = f"Linear: unknown issue input field(s) {unknown!r}"
        raise ValueError(msg)
    return "UpdateIssue", _UPDATE_ISSUE_QUERY, {"id": issue_id, "input": dict(fields)}


def _build_list_teams(params: dict[str, Any]) -> GraphQLRequest:
    variables: dict[str, Any] = {"first": _coerce_page_size(params.get("first"))}
    after = str(params.get("after") or "").strip()
    if after:
        variables["after"] = after
    return "ListTeams", _LIST_TEAMS_QUERY, variables


def _build_list_projects(params: dict[str, Any]) -> GraphQLRequest:
    variables: dict[str, Any] = {"first": _coerce_page_size(params.get("first"))}
    after = str(params.get("after") or "").strip()
    if after:
        variables["after"] = after
    return "ListProjects", _LIST_PROJECTS_QUERY, variables


def _coerce_page_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Linear: 'first' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Linear: 'first' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_SIZE)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Linear: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], GraphQLRequest]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_ISSUES: _build_list_issues,
    OP_GET_ISSUE: _build_get_issue,
    OP_CREATE_ISSUE: _build_create_issue,
    OP_UPDATE_ISSUE: _build_update_issue,
    OP_LIST_TEAMS: _build_list_teams,
    OP_LIST_PROJECTS: _build_list_projects,
}
