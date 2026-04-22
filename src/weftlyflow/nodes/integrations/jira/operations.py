"""Per-operation request builders for the Jira Cloud v3 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Issue keys and ids are URL-encoded because they can legitimately contain
``-`` / ``/`` / spaces in project-key collisions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.jira.constants import (
    API_VERSION_PREFIX,
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    OP_ADD_COMMENT,
    OP_CREATE_ISSUE,
    OP_DELETE_ISSUE,
    OP_GET_ISSUE,
    OP_SEARCH_ISSUES,
    OP_UPDATE_ISSUE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Jira: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_issue(params: dict[str, Any]) -> RequestSpec:
    issue_key = _required(params, "issue_key")
    path = f"{API_VERSION_PREFIX}/issue/{quote(issue_key, safe='')}"
    query: dict[str, Any] = {}
    fields = _coerce_string_list(params.get("fields"), field="fields")
    if fields:
        query["fields"] = ",".join(fields)
    expand = _coerce_string_list(params.get("expand"), field="expand")
    if expand:
        query["expand"] = ",".join(expand)
    return "GET", path, None, query


def _build_create_issue(params: dict[str, Any]) -> RequestSpec:
    project_key = _required(params, "project_key")
    summary = _required(params, "summary")
    issue_type = _required(params, "issue_type")
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    extra = params.get("extra_fields")
    if extra is not None:
        if not isinstance(extra, dict):
            msg = "Jira: 'extra_fields' must be a JSON object"
            raise ValueError(msg)
        fields.update(extra)
    return "POST", f"{API_VERSION_PREFIX}/issue", {"fields": fields}, {}


def _build_update_issue(params: dict[str, Any]) -> RequestSpec:
    issue_key = _required(params, "issue_key")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Jira: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    path = f"{API_VERSION_PREFIX}/issue/{quote(issue_key, safe='')}"
    return "PUT", path, {"fields": fields}, {}


def _build_delete_issue(params: dict[str, Any]) -> RequestSpec:
    issue_key = _required(params, "issue_key")
    path = f"{API_VERSION_PREFIX}/issue/{quote(issue_key, safe='')}"
    query: dict[str, Any] = {}
    delete_subtasks = params.get("delete_subtasks")
    if isinstance(delete_subtasks, bool):
        query["deleteSubtasks"] = "true" if delete_subtasks else "false"
    return "DELETE", path, None, query


def _build_search_issues(params: dict[str, Any]) -> RequestSpec:
    jql = str(params.get("jql") or "").strip()
    if not jql:
        msg = "Jira: 'jql' is required for search_issues"
        raise ValueError(msg)
    body: dict[str, Any] = {"jql": jql, "maxResults": _coerce_limit(params.get("max_results"))}
    start_at = params.get("start_at")
    if start_at not in (None, ""):
        body["startAt"] = _coerce_non_negative_int(start_at, field="start_at")
    fields = _coerce_string_list(params.get("fields"), field="fields")
    if fields:
        body["fields"] = fields
    return "POST", f"{API_VERSION_PREFIX}/search", body, {}


def _build_add_comment(params: dict[str, Any]) -> RequestSpec:
    issue_key = _required(params, "issue_key")
    body_text = str(params.get("body") or "")
    if not body_text.strip():
        msg = "Jira: 'body' is required for add_comment"
        raise ValueError(msg)
    path = f"{API_VERSION_PREFIX}/issue/{quote(issue_key, safe='')}/comment"
    comment_doc = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body_text}],
                },
            ],
        },
    }
    return "POST", path, comment_doc, {}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Jira: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Jira: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_SEARCH_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Jira: 'max_results' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Jira: 'max_results' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_SEARCH_LIMIT)


def _coerce_non_negative_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Jira: {field!r} must be a non-negative integer"
        raise ValueError(msg) from exc
    if value < 0:
        msg = f"Jira: {field!r} must be >= 0"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_ISSUE: _build_get_issue,
    OP_CREATE_ISSUE: _build_create_issue,
    OP_UPDATE_ISSUE: _build_update_issue,
    OP_DELETE_ISSUE: _build_delete_issue,
    OP_SEARCH_ISSUES: _build_search_issues,
    OP_ADD_COMMENT: _build_add_comment,
}
