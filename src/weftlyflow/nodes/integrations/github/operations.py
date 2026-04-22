"""Per-operation request builders for the GitHub node.

Every builder returns ``(http_method, path, json_body, query_params)`` that
the dispatcher in :mod:`weftlyflow.nodes.integrations.github.node` forwards
to :class:`httpx.AsyncClient`. Keeping the request construction here isolates
validation from IO and makes each operation unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.github.constants import (
    DEFAULT_LIST_PER_PAGE,
    ISSUE_STATE_OPEN,
    MAX_LIST_PER_PAGE,
    OP_CREATE_COMMENT,
    OP_CREATE_ISSUE,
    OP_GET_REPO,
    OP_LIST_ISSUES,
    VALID_ISSUE_STATES,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]
"""``(http_method, path, json_body, query_params)``.

``json_body`` is ``None`` for requests without a body (GET).
"""


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"GitHub: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_create_issue(params: dict[str, Any]) -> RequestSpec:
    owner, repo = _owner_and_repo(params)
    title = str(params.get("title") or "").strip()
    if not title:
        msg = "GitHub: create_issue requires 'title'"
        raise ValueError(msg)
    body: dict[str, Any] = {"title": title}
    text = params.get("body")
    if isinstance(text, str) and text.strip():
        body["body"] = text
    labels = _coerce_string_list(params.get("labels"), field="labels")
    if labels:
        body["labels"] = labels
    assignees = _coerce_string_list(params.get("assignees"), field="assignees")
    if assignees:
        body["assignees"] = assignees
    return "POST", f"/repos/{owner}/{repo}/issues", body, {}


def _build_list_issues(params: dict[str, Any]) -> RequestSpec:
    owner, repo = _owner_and_repo(params)
    state = str(params.get("state") or ISSUE_STATE_OPEN).strip()
    if state not in VALID_ISSUE_STATES:
        msg = (
            f"GitHub: invalid issue state {state!r} — must be one of "
            f"{sorted(VALID_ISSUE_STATES)}"
        )
        raise ValueError(msg)
    query: dict[str, Any] = {
        "state": state,
        "per_page": _coerce_per_page(params.get("per_page")),
    }
    labels = _coerce_string_list(params.get("labels"), field="labels")
    if labels:
        query["labels"] = ",".join(labels)
    page = params.get("page")
    if page is not None and str(page).strip():
        query["page"] = _coerce_positive_int(page, field="page")
    return "GET", f"/repos/{owner}/{repo}/issues", None, query


def _build_get_repo(params: dict[str, Any]) -> RequestSpec:
    owner, repo = _owner_and_repo(params)
    return "GET", f"/repos/{owner}/{repo}", None, {}


def _build_create_comment(params: dict[str, Any]) -> RequestSpec:
    owner, repo = _owner_and_repo(params)
    issue_number = _coerce_positive_int(params.get("issue_number"), field="issue_number")
    body_text = str(params.get("body") or "").strip()
    if not body_text:
        msg = "GitHub: create_comment requires 'body'"
        raise ValueError(msg)
    return (
        "POST",
        f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
        {"body": body_text},
        {},
    )


def _owner_and_repo(params: dict[str, Any]) -> tuple[str, str]:
    owner = str(params.get("owner") or "").strip()
    repo = str(params.get("repo") or "").strip()
    if not owner or not repo:
        msg = "GitHub: 'owner' and 'repo' are required"
        raise ValueError(msg)
    return owner, repo


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    msg = f"GitHub: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _coerce_per_page(raw: Any) -> int:
    if raw is None or raw == "":
        return DEFAULT_LIST_PER_PAGE
    value = _coerce_positive_int(raw, field="per_page")
    return min(value, MAX_LIST_PER_PAGE)


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"GitHub: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"GitHub: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CREATE_ISSUE: _build_create_issue,
    OP_LIST_ISSUES: _build_list_issues,
    OP_GET_REPO: _build_get_repo,
    OP_CREATE_COMMENT: _build_create_comment,
}
