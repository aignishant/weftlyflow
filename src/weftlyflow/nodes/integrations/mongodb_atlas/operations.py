"""Per-operation request builders for the MongoDB Atlas node.

Each builder returns ``(http_method, path, body, query)`` where ``path``
is relative to :data:`API_BASE_URL`. Atlas uses URL-variable paths for
project and cluster scoping (``/groups/{groupId}/clusters/{clusterName}``)
rather than query parameters or request bodies, so the builders embed
the IDs straight into the path.

Pagination is exposed via the standard Atlas ``pageNum`` / ``itemsPerPage``
query parameters; builders forward them only when supplied.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.mongodb_atlas.constants import (
    OP_GET_CLUSTER,
    OP_LIST_CLUSTERS,
    OP_LIST_DB_USERS,
    OP_LIST_PROJECTS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"MongoDB Atlas: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_projects(params: dict[str, Any]) -> RequestSpec:
    return "GET", "/groups", None, _paging(params)


def _build_list_clusters(params: dict[str, Any]) -> RequestSpec:
    group_id = _required_str(params, "group_id")
    return "GET", f"/groups/{group_id}/clusters", None, _paging(params)


def _build_get_cluster(params: dict[str, Any]) -> RequestSpec:
    group_id = _required_str(params, "group_id")
    cluster_name = _required_str(params, "cluster_name")
    return "GET", f"/groups/{group_id}/clusters/{cluster_name}", None, {}


def _build_list_db_users(params: dict[str, Any]) -> RequestSpec:
    group_id = _required_str(params, "group_id")
    return "GET", f"/groups/{group_id}/databaseUsers", None, _paging(params)


def _paging(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    page_num = params.get("page_num")
    if isinstance(page_num, int) and page_num > 0:
        out["pageNum"] = str(page_num)
    items_per_page = params.get("items_per_page")
    if isinstance(items_per_page, int) and items_per_page > 0:
        out["itemsPerPage"] = str(items_per_page)
    return out


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"MongoDB Atlas: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_PROJECTS: _build_list_projects,
    OP_LIST_CLUSTERS: _build_list_clusters,
    OP_GET_CLUSTER: _build_get_cluster,
    OP_LIST_DB_USERS: _build_list_db_users,
}
