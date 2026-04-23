"""Per-operation request builders for the Bitbucket Cloud node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://api.bitbucket.org/2.0/repositories/{workspace}/...``
or ``/2.0/workspaces/{workspace}/...`` — the workspace prefix is
attached by the node, not the builder.

Distinctive Bitbucket shapes:

* PR creation requires nested ``source.branch.name`` and
  ``destination.branch.name`` rather than flat ``head`` / ``base``
  strings (which is what GitHub uses).
* List endpoints accept a ``q`` BBQL filter expression — distinct from
  the ``where`` query string used by Xero.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.bitbucket.constants import (
    OP_CREATE_ISSUE,
    OP_CREATE_PULL_REQUEST,
    OP_GET_PULL_REQUEST,
    OP_GET_REPOSITORY,
    OP_LIST_ISSUES,
    OP_LIST_PULL_REQUESTS,
    OP_LIST_REPOSITORIES,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(
    operation: str,
    params: dict[str, Any],
    *,
    workspace: str,
) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`.

    Args:
        operation: Operation slug.
        params: Resolved per-item parameters from the node.
        workspace: Default workspace from the credential — used as the
            URL prefix when the per-call ``workspace`` param is empty.
    """
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Bitbucket: unsupported operation {operation!r}"
        raise ValueError(msg)
    effective_ws = str(params.get("workspace") or workspace or "").strip()
    if not effective_ws:
        msg = "Bitbucket: 'workspace' is required (set on the credential or per-call)"
        raise ValueError(msg)
    return builder(params, effective_ws)


def _build_list_repositories(params: dict[str, Any], workspace: str) -> RequestSpec:
    query: dict[str, Any] = {}
    role = str(params.get("role") or "").strip()
    if role:
        query["role"] = role
    bbql = str(params.get("q") or "").strip()
    if bbql:
        query["q"] = bbql
    page = params.get("page")
    if page not in (None, ""):
        query["page"] = _coerce_positive_int(page, field="page")
    pagelen = params.get("pagelen")
    if pagelen not in (None, ""):
        query["pagelen"] = _coerce_positive_int(pagelen, field="pagelen")
    return "GET", f"/2.0/repositories/{quote(workspace, safe='')}", None, query


def _build_get_repository(params: dict[str, Any], workspace: str) -> RequestSpec:
    repo = _required(params, "repo_slug")
    path = f"/2.0/repositories/{quote(workspace, safe='')}/{quote(repo, safe='')}"
    return "GET", path, None, {}


def _build_list_pull_requests(params: dict[str, Any], workspace: str) -> RequestSpec:
    repo = _required(params, "repo_slug")
    query: dict[str, Any] = {}
    state = str(params.get("state") or "").strip()
    if state:
        query["state"] = state
    pagelen = params.get("pagelen")
    if pagelen not in (None, ""):
        query["pagelen"] = _coerce_positive_int(pagelen, field="pagelen")
    path = (
        f"/2.0/repositories/{quote(workspace, safe='')}"
        f"/{quote(repo, safe='')}/pullrequests"
    )
    return "GET", path, None, query


def _build_get_pull_request(params: dict[str, Any], workspace: str) -> RequestSpec:
    repo = _required(params, "repo_slug")
    pr_id = _required(params, "pull_request_id")
    path = (
        f"/2.0/repositories/{quote(workspace, safe='')}"
        f"/{quote(repo, safe='')}/pullrequests/{quote(pr_id, safe='')}"
    )
    return "GET", path, None, {}


def _build_create_pull_request(params: dict[str, Any], workspace: str) -> RequestSpec:
    repo = _required(params, "repo_slug")
    title = _required(params, "title")
    source = _required(params, "source_branch")
    destination = str(params.get("destination_branch") or "").strip()
    body: dict[str, Any] = {
        "title": title,
        "source": {"branch": {"name": source}},
    }
    if destination:
        body["destination"] = {"branch": {"name": destination}}
    description = str(params.get("description") or "").strip()
    if description:
        body["description"] = description
    close_source_branch = params.get("close_source_branch")
    if isinstance(close_source_branch, bool):
        body["close_source_branch"] = close_source_branch
    path = (
        f"/2.0/repositories/{quote(workspace, safe='')}"
        f"/{quote(repo, safe='')}/pullrequests"
    )
    return "POST", path, body, {}


def _build_list_issues(params: dict[str, Any], workspace: str) -> RequestSpec:
    repo = _required(params, "repo_slug")
    query: dict[str, Any] = {}
    bbql = str(params.get("q") or "").strip()
    if bbql:
        query["q"] = bbql
    pagelen = params.get("pagelen")
    if pagelen not in (None, ""):
        query["pagelen"] = _coerce_positive_int(pagelen, field="pagelen")
    path = (
        f"/2.0/repositories/{quote(workspace, safe='')}"
        f"/{quote(repo, safe='')}/issues"
    )
    return "GET", path, None, query


def _build_create_issue(params: dict[str, Any], workspace: str) -> RequestSpec:
    repo = _required(params, "repo_slug")
    title = _required(params, "title")
    body: dict[str, Any] = {"title": title}
    content = str(params.get("content") or "").strip()
    if content:
        body["content"] = {"raw": content}
    kind = str(params.get("kind") or "").strip()
    if kind:
        body["kind"] = kind
    priority = str(params.get("priority") or "").strip()
    if priority:
        body["priority"] = priority
    path = (
        f"/2.0/repositories/{quote(workspace, safe='')}"
        f"/{quote(repo, safe='')}/issues"
    )
    return "POST", path, body, {}


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Bitbucket: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Bitbucket: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Bitbucket: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any], str], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_REPOSITORIES: _build_list_repositories,
    OP_GET_REPOSITORY: _build_get_repository,
    OP_LIST_PULL_REQUESTS: _build_list_pull_requests,
    OP_GET_PULL_REQUEST: _build_get_pull_request,
    OP_CREATE_PULL_REQUEST: _build_create_pull_request,
    OP_LIST_ISSUES: _build_list_issues,
    OP_CREATE_ISSUE: _build_create_issue,
}
