"""Per-operation request builders for the Facebook Graph node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to the version-prefixed base URL ``/{api_version}``.

Distinctive Graph shapes:

* Edges (``/{node_id}/{edge}``) are first-class — ``list_edge`` and
  ``create_edge`` accept a free-form edge name (``posts``, ``feed``,
  ``comments``, ``accounts``, ...).
* ``fields`` is a comma-separated query parameter that selects which
  scalar/edge fields to return — Facebook returns only ``id`` by
  default if omitted.
* Reads use GET; writes use POST with a form/JSON body; deletes use
  DELETE — there is no PATCH/PUT in the Graph API.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.facebook.constants import (
    OP_CREATE_EDGE,
    OP_DELETE_NODE,
    OP_GET_ME,
    OP_GET_NODE,
    OP_LIST_EDGE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Facebook: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_me(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    fields = str(params.get("fields") or "").strip()
    if fields:
        query["fields"] = fields
    return "GET", "/me", None, query


def _build_get_node(params: dict[str, Any]) -> RequestSpec:
    node_id = _required(params, "node_id")
    query: dict[str, Any] = {}
    fields = str(params.get("fields") or "").strip()
    if fields:
        query["fields"] = fields
    return "GET", f"/{quote(node_id, safe='')}", None, query


def _build_list_edge(params: dict[str, Any]) -> RequestSpec:
    node_id = _required(params, "node_id")
    edge = _required(params, "edge")
    query: dict[str, Any] = {}
    fields = str(params.get("fields") or "").strip()
    if fields:
        query["fields"] = fields
    limit = params.get("limit")
    if limit is not None and limit != "":
        query["limit"] = _coerce_positive_int(limit, field="limit")
    after = str(params.get("after") or "").strip()
    if after:
        query["after"] = after
    before = str(params.get("before") or "").strip()
    if before:
        query["before"] = before
    path = f"/{quote(node_id, safe='')}/{quote(edge, safe='')}"
    return "GET", path, None, query


def _build_create_edge(params: dict[str, Any]) -> RequestSpec:
    node_id = _required(params, "node_id")
    edge = _required(params, "edge")
    body = _coerce_body(params.get("body"))
    path = f"/{quote(node_id, safe='')}/{quote(edge, safe='')}"
    return "POST", path, body, {}


def _build_delete_node(params: dict[str, Any]) -> RequestSpec:
    node_id = _required(params, "node_id")
    return "DELETE", f"/{quote(node_id, safe='')}", None, {}


def _coerce_body(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        msg = "Facebook: 'body' is required"
        raise ValueError(msg)
    if not isinstance(raw, dict):
        msg = "Facebook: 'body' must be a JSON object"
        raise ValueError(msg)
    return raw


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Facebook: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Facebook: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Facebook: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_ME: _build_get_me,
    OP_GET_NODE: _build_get_node,
    OP_LIST_EDGE: _build_list_edge,
    OP_CREATE_EDGE: _build_create_edge,
    OP_DELETE_NODE: _build_delete_node,
}
