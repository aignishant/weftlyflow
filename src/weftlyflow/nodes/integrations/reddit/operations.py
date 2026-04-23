"""Per-operation request builders for the Reddit node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://oauth.reddit.com``.

Reddit's submission endpoint (``/api/submit``) is the oddball: it
consumes ``application/x-www-form-urlencoded`` rather than JSON. The
builder returns the form as the ``body`` dict and the node knows to
switch Content-Type based on the operation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.reddit.constants import (
    KIND_LINK,
    KIND_SELF,
    OP_GET_ME,
    OP_GET_SUBREDDIT,
    OP_LIST_HOT,
    OP_SUBMIT_POST,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Reddit: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_me(_params: dict[str, Any]) -> RequestSpec:
    return "GET", "/api/v1/me", None, {}


def _build_submit_post(params: dict[str, Any]) -> RequestSpec:
    subreddit = _required_str(params, "subreddit")
    title = _required_str(params, "title")
    kind = str(params.get("kind") or KIND_SELF).strip() or KIND_SELF
    if kind not in (KIND_LINK, KIND_SELF):
        msg = f"Reddit: 'kind' must be 'link' or 'self' — got {kind!r}"
        raise ValueError(msg)
    form: dict[str, Any] = {
        "sr": subreddit,
        "title": title,
        "kind": kind,
        "api_type": "json",
    }
    if kind == KIND_LINK:
        form["url"] = _required_str(params, "url")
    else:
        text = str(params.get("text") or "").strip()
        if text:
            form["text"] = text
    nsfw = params.get("nsfw")
    if isinstance(nsfw, bool):
        form["nsfw"] = "true" if nsfw else "false"
    return "POST", "/api/submit", form, {}


def _build_get_subreddit(params: dict[str, Any]) -> RequestSpec:
    subreddit = _required_str(params, "subreddit")
    return "GET", f"/r/{subreddit}/about", None, {}


def _build_list_hot(params: dict[str, Any]) -> RequestSpec:
    subreddit = _required_str(params, "subreddit")
    query: dict[str, Any] = {}
    limit = params.get("limit")
    if isinstance(limit, int) and limit > 0:
        query["limit"] = str(limit)
    after = str(params.get("after") or "").strip()
    if after:
        query["after"] = after
    return "GET", f"/r/{subreddit}/hot", None, query


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Reddit: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_ME: _build_get_me,
    OP_SUBMIT_POST: _build_submit_post,
    OP_GET_SUBREDDIT: _build_get_subreddit,
    OP_LIST_HOT: _build_list_hot,
}
