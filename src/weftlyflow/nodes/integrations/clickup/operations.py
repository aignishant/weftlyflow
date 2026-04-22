"""Per-operation request builders for the ClickUp v2 task node.

Each builder returns ``(http_method, path, json_body, query_params)``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.clickup.constants import (
    API_VERSION_PREFIX,
    OP_CREATE_TASK,
    OP_DELETE_TASK,
    OP_GET_TASK,
    OP_LIST_TASKS,
    OP_UPDATE_TASK,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_MIN_PRIORITY: int = 1
_MAX_PRIORITY: int = 4

_UPDATE_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "status",
        "priority",
        "due_date",
        "due_date_time",
        "time_estimate",
        "start_date",
        "start_date_time",
        "assignees",
        "archived",
        "parent",
    },
)


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"ClickUp: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_create_task(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    name = _required(params, "name")
    body: dict[str, Any] = {"name": name}
    description = str(params.get("description") or "")
    if description:
        body["description"] = description
    assignees = params.get("assignees")
    if assignees is not None:
        body["assignees"] = _coerce_int_list(assignees, field="assignees")
    status = str(params.get("status") or "").strip()
    if status:
        body["status"] = status
    priority = params.get("priority")
    if priority not in (None, ""):
        body["priority"] = _coerce_priority(priority)
    extras = params.get("extra_fields")
    if extras is not None:
        if not isinstance(extras, dict):
            msg = "ClickUp: 'extra_fields' must be a JSON object"
            raise ValueError(msg)
        body.update(extras)
    path = f"{API_VERSION_PREFIX}/list/{quote(list_id, safe='')}/task"
    return "POST", path, body, {}


def _build_get_task(params: dict[str, Any]) -> RequestSpec:
    task_id = _required(params, "task_id")
    path = f"{API_VERSION_PREFIX}/task/{quote(task_id, safe='')}"
    return "GET", path, None, {}


def _build_update_task(params: dict[str, Any]) -> RequestSpec:
    task_id = _required(params, "task_id")
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "ClickUp: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    for key in updates:
        if key not in _UPDATE_ALLOWED_FIELDS:
            msg = f"ClickUp: unknown task field {key!r}"
            raise ValueError(msg)
    path = f"{API_VERSION_PREFIX}/task/{quote(task_id, safe='')}"
    return "PUT", path, dict(updates), {}


def _build_delete_task(params: dict[str, Any]) -> RequestSpec:
    task_id = _required(params, "task_id")
    path = f"{API_VERSION_PREFIX}/task/{quote(task_id, safe='')}"
    return "DELETE", path, None, {}


def _build_list_tasks(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    query: dict[str, Any] = {}
    archived = params.get("archived")
    if isinstance(archived, bool):
        query["archived"] = "true" if archived else "false"
    page = params.get("page")
    if page not in (None, ""):
        query["page"] = _coerce_non_negative_int(page, field="page")
    order_by = str(params.get("order_by") or "").strip()
    if order_by:
        query["order_by"] = order_by
    subtasks = params.get("subtasks")
    if isinstance(subtasks, bool):
        query["subtasks"] = "true" if subtasks else "false"
    statuses = _coerce_string_list(params.get("statuses"), field="statuses")
    if statuses:
        query["statuses[]"] = statuses
    path = f"{API_VERSION_PREFIX}/list/{quote(list_id, safe='')}/task"
    return "GET", path, None, query


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"ClickUp: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_int_list(raw: Any, *, field: str) -> list[int]:
    if not isinstance(raw, list):
        msg = f"ClickUp: {field!r} must be a list of user ids"
        raise ValueError(msg)
    out: list[int] = []
    for value in raw:
        try:
            out.append(int(value))
        except (TypeError, ValueError) as exc:
            msg = f"ClickUp: {field!r} entries must be integer user ids"
            raise ValueError(msg) from exc
    return out


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"ClickUp: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _coerce_priority(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "ClickUp: 'priority' must be an integer in 1..4"
        raise ValueError(msg) from exc
    if value < _MIN_PRIORITY or value > _MAX_PRIORITY:
        msg = "ClickUp: 'priority' must be in 1..4"
        raise ValueError(msg)
    return value


def _coerce_non_negative_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"ClickUp: {field!r} must be a non-negative integer"
        raise ValueError(msg) from exc
    if value < 0:
        msg = f"ClickUp: {field!r} must be >= 0"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CREATE_TASK: _build_create_task,
    OP_GET_TASK: _build_get_task,
    OP_UPDATE_TASK: _build_update_task,
    OP_DELETE_TASK: _build_delete_task,
    OP_LIST_TASKS: _build_list_tasks,
}
