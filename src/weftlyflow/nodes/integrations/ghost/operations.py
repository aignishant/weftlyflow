"""Per-operation request builders for the Ghost Admin node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``<base_url>/ghost/api/admin``.

Distinctive Ghost shapes:

* List and mutation envelopes use a single-key wrapper — posts go in
  and come out as ``{"posts": [{...}]}``, members as ``{"members":
  [...]}``. The node wraps outgoing user-supplied fields accordingly.
* Update requires the current ``updated_at`` in the body for
  optimistic concurrency (Ghost rejects with 409 on drift).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.ghost.constants import (
    ADMIN_API_BASE,
    OP_CREATE_MEMBER,
    OP_CREATE_POST,
    OP_DELETE_POST,
    OP_GET_POST,
    OP_LIST_MEMBERS,
    OP_LIST_POSTS,
    OP_UPDATE_POST,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Ghost: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_posts(params: dict[str, Any]) -> RequestSpec:
    query = _collect_list_query(params)
    return "GET", f"{ADMIN_API_BASE}/posts/", None, query


def _build_get_post(params: dict[str, Any]) -> RequestSpec:
    post_id = _required(params, "post_id")
    query: dict[str, Any] = {}
    include = str(params.get("include") or "").strip()
    if include:
        query["include"] = include
    return "GET", f"{ADMIN_API_BASE}/posts/{quote(post_id, safe='')}/", None, query


def _build_create_post(params: dict[str, Any]) -> RequestSpec:
    title = _required(params, "title")
    post: dict[str, Any] = {"title": title}
    _merge_optional_post_fields(post, params)
    return "POST", f"{ADMIN_API_BASE}/posts/", {"posts": [post]}, {}


def _build_update_post(params: dict[str, Any]) -> RequestSpec:
    post_id = _required(params, "post_id")
    updated_at = str(params.get("updated_at") or "").strip()
    if not updated_at:
        msg = "Ghost: 'updated_at' is required for updates (optimistic concurrency)"
        raise ValueError(msg)
    post: dict[str, Any] = {"updated_at": updated_at}
    _merge_optional_post_fields(post, params)
    if len(post) == 1:
        msg = "Ghost: update requires at least one field besides 'updated_at'"
        raise ValueError(msg)
    path = f"{ADMIN_API_BASE}/posts/{quote(post_id, safe='')}/"
    return "PUT", path, {"posts": [post]}, {}


def _build_delete_post(params: dict[str, Any]) -> RequestSpec:
    post_id = _required(params, "post_id")
    path = f"{ADMIN_API_BASE}/posts/{quote(post_id, safe='')}/"
    return "DELETE", path, None, {}


def _build_list_members(params: dict[str, Any]) -> RequestSpec:
    query = _collect_list_query(params)
    return "GET", f"{ADMIN_API_BASE}/members/", None, query


def _build_create_member(params: dict[str, Any]) -> RequestSpec:
    email = _required(params, "email")
    member: dict[str, Any] = {"email": email}
    name = str(params.get("name") or "").strip()
    if name:
        member["name"] = name
    note = str(params.get("note") or "").strip()
    if note:
        member["note"] = note
    labels = params.get("labels")
    if isinstance(labels, list) and labels:
        member["labels"] = [str(lbl) for lbl in labels]
    return "POST", f"{ADMIN_API_BASE}/members/", {"members": [member]}, {}


def _collect_list_query(params: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for key in ("limit", "page", "filter", "order", "include", "fields"):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = _stringify(value)
    return query


def _merge_optional_post_fields(post: dict[str, Any], params: dict[str, Any]) -> None:
    for key in (
        "html",
        "lexical",
        "status",
        "slug",
        "custom_excerpt",
        "featured",
        "visibility",
    ):
        value = params.get(key)
        if value in (None, ""):
            continue
        post[key] = value
    tags = params.get("tags")
    if isinstance(tags, list) and tags:
        post["tags"] = tags


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Ghost: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_POSTS: _build_list_posts,
    OP_GET_POST: _build_get_post,
    OP_CREATE_POST: _build_create_post,
    OP_UPDATE_POST: _build_update_post,
    OP_DELETE_POST: _build_delete_post,
    OP_LIST_MEMBERS: _build_list_members,
    OP_CREATE_MEMBER: _build_create_member,
}
