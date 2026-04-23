"""Per-operation request builders for the Harvest node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://api.harvestapp.com``.

Harvest has two shapes worth noting:

* ``create_time_entry`` accepts **either** a duration (``hours``) or a
  timer style (``started_time``/``ended_time``) — the builder forwards
  whichever the caller supplied rather than forcing one.
* List endpoints expose pagination through ``page`` and ``per_page``
  query parameters; the builders funnel these into the query slot
  rather than the body.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.harvest.constants import (
    OP_CREATE_TIME_ENTRY,
    OP_GET_USER_ME,
    OP_LIST_PROJECTS,
    OP_LIST_TIME_ENTRIES,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Harvest: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_time_entries(params: dict[str, Any]) -> RequestSpec:
    query = _paging(params)
    for key in ("user_id", "project_id", "client_id", "from", "to"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            query[key] = value.strip()
        elif isinstance(value, int):
            query[key] = str(value)
    return "GET", "/v2/time_entries", None, query


def _build_create_time_entry(params: dict[str, Any]) -> RequestSpec:
    body: dict[str, Any] = {
        "project_id": _required_scalar(params, "project_id"),
        "task_id": _required_scalar(params, "task_id"),
        "spent_date": _required_str(params, "spent_date"),
    }
    hours = params.get("hours")
    if isinstance(hours, (int, float)):
        body["hours"] = hours
    started = str(params.get("started_time") or "").strip()
    ended = str(params.get("ended_time") or "").strip()
    if started:
        body["started_time"] = started
    if ended:
        body["ended_time"] = ended
    notes = str(params.get("notes") or "").strip()
    if notes:
        body["notes"] = notes
    user_id = params.get("user_id")
    if isinstance(user_id, (int, str)) and str(user_id).strip():
        body["user_id"] = _as_id(user_id)
    if "hours" not in body and "started_time" not in body:
        msg = "Harvest: supply either 'hours' or 'started_time' for create_time_entry"
        raise ValueError(msg)
    return "POST", "/v2/time_entries", body, {}


def _build_list_projects(params: dict[str, Any]) -> RequestSpec:
    query = _paging(params)
    for key in ("is_active", "client_id", "updated_since"):
        value = params.get(key)
        if isinstance(value, bool):
            query[key] = "true" if value else "false"
        elif isinstance(value, str) and value.strip():
            query[key] = value.strip()
        elif isinstance(value, int):
            query[key] = str(value)
    return "GET", "/v2/projects", None, query


def _build_get_user_me(_params: dict[str, Any]) -> RequestSpec:
    return "GET", "/v2/users/me", None, {}


def _paging(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    page = params.get("page")
    if isinstance(page, int) and page > 0:
        out["page"] = str(page)
    per_page = params.get("per_page")
    if isinstance(per_page, int) and per_page > 0:
        out["per_page"] = str(per_page)
    return out


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Harvest: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_scalar(params: dict[str, Any], key: str) -> int | str:
    raw = params.get(key)
    if isinstance(raw, int):
        return raw
    value = str(raw or "").strip()
    if not value:
        msg = f"Harvest: {key!r} is required"
        raise ValueError(msg)
    return _as_id(value)


def _as_id(value: Any) -> int | str:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return text


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_TIME_ENTRIES: _build_list_time_entries,
    OP_CREATE_TIME_ENTRY: _build_create_time_entry,
    OP_LIST_PROJECTS: _build_list_projects,
    OP_GET_USER_ME: _build_get_user_me,
}
