"""Per-operation request builders for the Notion node.

Each builder returns ``(http_method, path, json_body)``. ``json_body`` is
``None`` for GET requests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.notion.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    OP_CREATE_PAGE,
    OP_QUERY_DATABASE,
    OP_RETRIEVE_PAGE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Notion: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_query_database(params: dict[str, Any]) -> RequestSpec:
    database_id = _required(params, "database_id")
    body: dict[str, Any] = {}
    filter_payload = params.get("filter")
    if isinstance(filter_payload, dict):
        body["filter"] = filter_payload
    sorts_payload = params.get("sorts")
    if isinstance(sorts_payload, list):
        body["sorts"] = [dict(s) for s in sorts_payload if isinstance(s, dict)]
    page_size = _coerce_page_size(params.get("page_size"))
    body["page_size"] = page_size
    start_cursor = str(params.get("start_cursor") or "").strip()
    if start_cursor:
        body["start_cursor"] = start_cursor
    return "POST", f"/v1/databases/{database_id}/query", body


def _build_create_page(params: dict[str, Any]) -> RequestSpec:
    parent_db = str(params.get("parent_database_id") or "").strip()
    parent_page = str(params.get("parent_page_id") or "").strip()
    if not parent_db and not parent_page:
        msg = "Notion: create_page requires 'parent_database_id' or 'parent_page_id'"
        raise ValueError(msg)
    parent: dict[str, str] = (
        {"database_id": parent_db} if parent_db else {"page_id": parent_page}
    )
    properties = params.get("properties")
    if not isinstance(properties, dict):
        msg = "Notion: 'properties' must be a JSON object"
        raise ValueError(msg)
    body: dict[str, Any] = {"parent": parent, "properties": properties}
    children = params.get("children")
    if isinstance(children, list):
        body["children"] = [dict(c) for c in children if isinstance(c, dict)]
    return "POST", "/v1/pages", body


def _build_retrieve_page(params: dict[str, Any]) -> RequestSpec:
    page_id = _required(params, "page_id")
    return "GET", f"/v1/pages/{page_id}", None


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Notion: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_page_size(raw: Any) -> int:
    if raw is None or raw == "":
        return DEFAULT_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Notion: 'page_size' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Notion: 'page_size' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_SIZE)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_QUERY_DATABASE: _build_query_database,
    OP_CREATE_PAGE: _build_create_page,
    OP_RETRIEVE_PAGE: _build_retrieve_page,
}
