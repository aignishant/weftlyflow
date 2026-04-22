"""Per-operation request builders for the GitLab v4 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Project IDs must be URL-encoded when they are namespaced paths
(``group/subgroup/repo``) — GitLab requires the slashes to become
``%2F``. That happens here via :func:`urllib.parse.quote` with an empty
``safe`` set.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.gitlab.constants import (
    API_VERSION_PREFIX,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    OP_ADD_COMMENT,
    OP_CREATE_ISSUE,
    OP_GET_ISSUE,
    OP_LIST_ISSUES,
    OP_LIST_MERGE_REQUESTS,
    OP_UPDATE_ISSUE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_UPDATE_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "assignee_ids",
        "labels",
        "state_event",
        "milestone_id",
        "due_date",
        "discussion_locked",
        "confidential",
    },
)
_ISSUE_STATES: frozenset[str] = frozenset({"opened", "closed", "all"})
_MR_STATES: frozenset[str] = frozenset({"opened", "closed", "merged", "all"})


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"GitLab: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_issue(params: dict[str, Any]) -> RequestSpec:
    project = _required_project(params)
    iid = _required_iid(params)
    path = f"{API_VERSION_PREFIX}/projects/{project}/issues/{iid}"
    return "GET", path, None, {}


def _build_create_issue(params: dict[str, Any]) -> RequestSpec:
    project = _required_project(params)
    title = _required(params, "title")
    body: dict[str, Any] = {"title": title}
    description = str(params.get("description") or "")
    if description:
        body["description"] = description
    labels = _coerce_string_list(params.get("labels"), field="labels")
    if labels:
        body["labels"] = ",".join(labels)
    assignee_ids = params.get("assignee_ids")
    if assignee_ids is not None:
        body["assignee_ids"] = _coerce_int_list(assignee_ids, field="assignee_ids")
    path = f"{API_VERSION_PREFIX}/projects/{project}/issues"
    return "POST", path, body, {}


def _build_update_issue(params: dict[str, Any]) -> RequestSpec:
    project = _required_project(params)
    iid = _required_iid(params)
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "GitLab: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    for key in updates:
        if key not in _UPDATE_ALLOWED_FIELDS:
            msg = f"GitLab: unknown issue field {key!r}"
            raise ValueError(msg)
    path = f"{API_VERSION_PREFIX}/projects/{project}/issues/{iid}"
    return "PUT", path, dict(updates), {}


def _build_list_issues(params: dict[str, Any]) -> RequestSpec:
    project = _required_project(params)
    query: dict[str, Any] = {"per_page": _coerce_limit(params.get("per_page"))}
    state = str(params.get("state") or "").strip().lower()
    if state:
        if state not in _ISSUE_STATES:
            msg = f"GitLab: invalid issue state {state!r}"
            raise ValueError(msg)
        query["state"] = state
    labels = _coerce_string_list(params.get("labels"), field="labels")
    if labels:
        query["labels"] = ",".join(labels)
    search = str(params.get("search") or "").strip()
    if search:
        query["search"] = search
    path = f"{API_VERSION_PREFIX}/projects/{project}/issues"
    return "GET", path, None, query


def _build_add_comment(params: dict[str, Any]) -> RequestSpec:
    project = _required_project(params)
    iid = _required_iid(params)
    body_text = str(params.get("body") or "")
    if not body_text.strip():
        msg = "GitLab: 'body' is required for add_comment"
        raise ValueError(msg)
    path = f"{API_VERSION_PREFIX}/projects/{project}/issues/{iid}/notes"
    return "POST", path, {"body": body_text}, {}


def _build_list_merge_requests(params: dict[str, Any]) -> RequestSpec:
    project = _required_project(params)
    query: dict[str, Any] = {"per_page": _coerce_limit(params.get("per_page"))}
    state = str(params.get("state") or "").strip().lower()
    if state:
        if state not in _MR_STATES:
            msg = f"GitLab: invalid merge-request state {state!r}"
            raise ValueError(msg)
        query["state"] = state
    target_branch = str(params.get("target_branch") or "").strip()
    if target_branch:
        query["target_branch"] = target_branch
    path = f"{API_VERSION_PREFIX}/projects/{project}/merge_requests"
    return "GET", path, None, query


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"GitLab: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_project(params: dict[str, Any]) -> str:
    value = _required(params, "project_id")
    return quote(value, safe="")


def _required_iid(params: dict[str, Any]) -> str:
    raw = params.get("issue_iid")
    if raw is None or raw == "":
        msg = "GitLab: 'issue_iid' is required"
        raise ValueError(msg)
    try:
        iid = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "GitLab: 'issue_iid' must be an integer"
        raise ValueError(msg) from exc
    if iid < 1:
        msg = "GitLab: 'issue_iid' must be >= 1"
        raise ValueError(msg)
    return str(iid)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"GitLab: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _coerce_int_list(raw: Any, *, field: str) -> list[int]:
    if not isinstance(raw, list):
        msg = f"GitLab: {field!r} must be a list of integers"
        raise ValueError(msg)
    out: list[int] = []
    for value in raw:
        try:
            out.append(int(value))
        except (TypeError, ValueError) as exc:
            msg = f"GitLab: {field!r} entries must be integers"
            raise ValueError(msg) from exc
    return out


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "GitLab: 'per_page' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "GitLab: 'per_page' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_ISSUE: _build_get_issue,
    OP_CREATE_ISSUE: _build_create_issue,
    OP_UPDATE_ISSUE: _build_update_issue,
    OP_LIST_ISSUES: _build_list_issues,
    OP_ADD_COMMENT: _build_add_comment,
    OP_LIST_MERGE_REQUESTS: _build_list_merge_requests,
}
