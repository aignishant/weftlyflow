"""Per-operation request builders for the App Store Connect node.

Each builder returns ``(http_method, path, query)``. Paths are
relative to :data:`API_BASE_URL`. Auth is injected by the credential,
so builders deal only with URL shape and query parameters.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.asc.constants import (
    OP_GET_APP,
    OP_LIST_APPS,
    OP_LIST_BETA_TESTERS,
    OP_LIST_BUILDS,
)

RequestSpec = tuple[str, str, dict[str, str]]

_MAX_LIMIT: int = 200


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"ASC: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_apps(params: dict[str, Any]) -> RequestSpec:
    return "GET", "/v1/apps", _limit_query(params)


def _build_get_app(params: dict[str, Any]) -> RequestSpec:
    app_id = _required_str(params, "app_id")
    return "GET", f"/v1/apps/{app_id}", {}


def _build_list_builds(params: dict[str, Any]) -> RequestSpec:
    query = _limit_query(params)
    app_id = str(params.get("app_id") or "").strip()
    if app_id:
        query["filter[app]"] = app_id
    return "GET", "/v1/builds", query


def _build_list_beta_testers(params: dict[str, Any]) -> RequestSpec:
    return "GET", "/v1/betaTesters", _limit_query(params)


def _limit_query(params: dict[str, Any]) -> dict[str, str]:
    limit = str(params.get("limit") or "").strip()
    if not limit:
        return {}
    try:
        value = int(limit)
    except ValueError as exc:
        msg = f"ASC: 'limit' must be an integer — got {limit!r}"
        raise ValueError(msg) from exc
    if value < 1 or value > _MAX_LIMIT:
        msg = f"ASC: 'limit' must be between 1 and {_MAX_LIMIT}"
        raise ValueError(msg)
    return {"limit": str(value)}


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"ASC: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_APPS: _build_list_apps,
    OP_GET_APP: _build_get_app,
    OP_LIST_BUILDS: _build_list_builds,
    OP_LIST_BETA_TESTERS: _build_list_beta_testers,
}
