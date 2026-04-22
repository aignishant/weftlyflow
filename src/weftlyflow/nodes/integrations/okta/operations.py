"""Per-operation request builders for the Okta v1 node.

Each builder returns ``(http_method, path, json_body, query_params)``.
Paths are prefixed with ``/`` and the node layer prepends the shared
``https://<org>.okta.com/api/v1`` base URL.

Okta expresses users via a nested ``profile`` object. ``create_user``
supports an optional ``credentials.password.value`` and an activation
toggle encoded in the ``activate`` query parameter. ``deactivate_user``
is a ``POST`` to the ``/lifecycle/deactivate`` subresource — mapping to
the Okta REST convention for lifecycle transitions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.okta.constants import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    OP_CREATE_USER,
    OP_DEACTIVATE_USER,
    OP_GET_USER,
    OP_LIST_GROUPS,
    OP_LIST_USERS,
    OP_UPDATE_USER,
    USER_PROFILE_REQUIRED_FIELDS,
    USER_UPDATE_PROFILE_FIELDS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Okta: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_users(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_limit(params.get("limit"))}
    search = str(params.get("search") or "").strip()
    if search:
        query["search"] = search
    filter_expr = str(params.get("filter") or "").strip()
    if filter_expr:
        query["filter"] = filter_expr
    after = str(params.get("after") or "").strip()
    if after:
        query["after"] = after
    return "GET", "/users", None, query


def _build_get_user(params: dict[str, Any]) -> RequestSpec:
    user_id = _required(params, "user_id")
    return "GET", f"/users/{quote(user_id, safe='')}", None, {}


def _build_create_user(params: dict[str, Any]) -> RequestSpec:
    profile = params.get("profile")
    if not isinstance(profile, dict) or not profile:
        msg = "Okta: 'profile' must be a non-empty JSON object"
        raise ValueError(msg)
    missing = [f for f in USER_PROFILE_REQUIRED_FIELDS if not profile.get(f)]
    if missing:
        msg = f"Okta: 'profile' is missing required field(s) {missing!r}"
        raise ValueError(msg)
    body: dict[str, Any] = {"profile": dict(profile)}
    password = str(params.get("password") or "").strip()
    if password:
        body["credentials"] = {"password": {"value": password}}
    groups = _coerce_string_list(params.get("group_ids"), field="group_ids")
    if groups:
        body["groupIds"] = groups
    query: dict[str, Any] = {"activate": _coerce_bool(params.get("activate"))}
    return "POST", "/users", body, query


def _build_update_user(params: dict[str, Any]) -> RequestSpec:
    user_id = _required(params, "user_id")
    profile = params.get("profile")
    if not isinstance(profile, dict) or not profile:
        msg = "Okta: 'profile' must be a non-empty JSON object"
        raise ValueError(msg)
    unknown = [k for k in profile if k not in USER_UPDATE_PROFILE_FIELDS]
    if unknown:
        msg = f"Okta: unknown profile field(s) {unknown!r}"
        raise ValueError(msg)
    body: dict[str, Any] = {"profile": dict(profile)}
    return "POST", f"/users/{quote(user_id, safe='')}", body, {}


def _build_deactivate_user(params: dict[str, Any]) -> RequestSpec:
    user_id = _required(params, "user_id")
    query: dict[str, Any] = {}
    send_email = params.get("send_email")
    if send_email is not None:
        query["sendEmail"] = _coerce_bool(send_email)
    path = f"/users/{quote(user_id, safe='')}/lifecycle/deactivate"
    return "POST", path, None, query


def _build_list_groups(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_limit(params.get("limit"))}
    q = str(params.get("q") or "").strip()
    if q:
        query["q"] = q
    filter_expr = str(params.get("filter") or "").strip()
    if filter_expr:
        query["filter"] = filter_expr
    after = str(params.get("after") or "").strip()
    if after:
        query["after"] = after
    return "GET", "/groups", None, query


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Okta: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Okta: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIMIT)


def _coerce_bool(raw: Any) -> str:
    if isinstance(raw, bool):
        return "true" if raw else "false"
    if raw in (None, ""):
        return "true"
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes"}:
        return "true"
    if text in {"false", "0", "no"}:
        return "false"
    msg = f"Okta: boolean flag must be true/false, got {raw!r}"
    raise ValueError(msg)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Okta: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Okta: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_USERS: _build_list_users,
    OP_GET_USER: _build_get_user,
    OP_CREATE_USER: _build_create_user,
    OP_UPDATE_USER: _build_update_user,
    OP_DEACTIVATE_USER: _build_deactivate_user,
    OP_LIST_GROUPS: _build_list_groups,
}
