"""Per-operation request builders for the Asana node.

Each builder returns ``(http_method, path, body, query)``. Paths are
prefixed with :data:`API_BASE_URL` by the node layer.

Asana wraps every request/response payload in a top-level ``data``
envelope — creates and updates send ``{"data": {...}}``, and list
endpoints return ``{"data": [...]}``. The builders handle the request
side of that envelope so the node surface stays symmetric.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.asana.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    OP_ADD_COMMENT,
    OP_CREATE_TASK,
    OP_DELETE_TASK,
    OP_GET_TASK,
    OP_LIST_TASKS,
    OP_UPDATE_TASK,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Asana: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_tasks(params: dict[str, Any]) -> RequestSpec:
    project = str(params.get("project") or "").strip()
    assignee = str(params.get("assignee") or "").strip()
    workspace = str(params.get("workspace") or "").strip()
    if not project and not (assignee and workspace):
        msg = (
            "Asana: list_tasks requires 'project' OR "
            "('assignee' AND 'workspace')"
        )
        raise ValueError(msg)
    query: dict[str, Any] = {"limit": _coerce_page_size(params.get("limit"))}
    if project:
        query["project"] = project
    if assignee:
        query["assignee"] = assignee
    if workspace:
        query["workspace"] = workspace
    completed_since = str(params.get("completed_since") or "").strip()
    if completed_since:
        query["completed_since"] = completed_since
    offset = str(params.get("offset") or "").strip()
    if offset:
        query["offset"] = offset
    fields = _coerce_string_list(params.get("opt_fields"), field="opt_fields")
    if fields:
        query["opt_fields"] = ",".join(fields)
    return "GET", "/tasks", None, query


def _build_get_task(params: dict[str, Any]) -> RequestSpec:
    task_id = _required_id(params, "task_id")
    fields = _coerce_string_list(params.get("opt_fields"), field="opt_fields")
    query: dict[str, Any] = {}
    if fields:
        query["opt_fields"] = ",".join(fields)
    return "GET", f"/tasks/{task_id}", None, query


def _build_create_task(params: dict[str, Any]) -> RequestSpec:
    document = params.get("document")
    if not isinstance(document, dict) or not document:
        msg = "Asana: 'document' must be a non-empty JSON object"
        raise ValueError(msg)
    if not str(document.get("name") or "").strip():
        msg = "Asana: create_task requires 'document.name'"
        raise ValueError(msg)
    return "POST", "/tasks", {"data": dict(document)}, {}


def _build_update_task(params: dict[str, Any]) -> RequestSpec:
    task_id = _required_id(params, "task_id")
    document = params.get("document")
    if not isinstance(document, dict) or not document:
        msg = "Asana: 'document' must be a non-empty JSON object"
        raise ValueError(msg)
    return "PUT", f"/tasks/{task_id}", {"data": dict(document)}, {}


def _build_delete_task(params: dict[str, Any]) -> RequestSpec:
    task_id = _required_id(params, "task_id")
    return "DELETE", f"/tasks/{task_id}", None, {}


def _build_add_comment(params: dict[str, Any]) -> RequestSpec:
    task_id = _required_id(params, "task_id")
    text = str(params.get("text") or "").strip()
    html_text = str(params.get("html_text") or "").strip()
    if not text and not html_text:
        msg = "Asana: add_comment requires 'text' or 'html_text'"
        raise ValueError(msg)
    body: dict[str, Any] = {}
    if html_text:
        body["html_text"] = html_text
    else:
        body["text"] = text
    is_pinned = params.get("is_pinned")
    if is_pinned is not None:
        body["is_pinned"] = bool(is_pinned)
    return "POST", f"/tasks/{task_id}/stories", {"data": body}, {}


def _coerce_page_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Asana: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Asana: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_SIZE)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Asana: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required_id(params: dict[str, Any], key: str) -> str:
    raw = params.get(key)
    if raw in (None, ""):
        msg = f"Asana: {key!r} is required"
        raise ValueError(msg)
    return quote(str(raw).strip(), safe="")


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_TASKS: _build_list_tasks,
    OP_GET_TASK: _build_get_task,
    OP_CREATE_TASK: _build_create_task,
    OP_UPDATE_TASK: _build_update_task,
    OP_DELETE_TASK: _build_delete_task,
    OP_ADD_COMMENT: _build_add_comment,
}
