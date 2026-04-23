"""Per-operation request builders for the Contentful node.

Each builder returns ``(http_method, path, body, query, version)``
where ``version`` is the ``X-Contentful-Version`` header value (``None``
for reads/creates, required integer for updates/publish/delete).

Distinctive Contentful shapes:

* Writes use PUT with a mandatory ``X-Contentful-Version`` header
  carrying the *current* ``sys.version``. The server returns 409 on a
  mismatch — Contentful's optimistic-concurrency lever.
* ``publish_entry`` is ``PUT /entries/{id}/published`` with an empty
  body — still versioned.
* ``list_entries`` supports a mixed filter query that includes
  dot-suffixed operators (``sys.id[in]``, ``fields.slug[ne]``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.contentful.constants import (
    OP_CREATE_ENTRY,
    OP_DELETE_ENTRY,
    OP_GET_ASSET,
    OP_GET_ENTRY,
    OP_LIST_ENTRIES,
    OP_PUBLISH_ENTRY,
    OP_UPDATE_ENTRY,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any], int | None]


def build_request(
    operation: str,
    params: dict[str, Any],
    *,
    space_id: str,
    environment: str,
) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    if not space_id:
        msg = "Contentful: 'space_id' is required"
        raise ValueError(msg)
    if not environment:
        msg = "Contentful: 'environment' is required"
        raise ValueError(msg)
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Contentful: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params, space_id, environment)


def _space_env_prefix(space_id: str, environment: str) -> str:
    return (
        f"/spaces/{quote(space_id, safe='')}"
        f"/environments/{quote(environment, safe='')}"
    )


def _build_get_entry(
    params: dict[str, Any],
    space_id: str,
    environment: str,
) -> RequestSpec:
    entry_id = _required(params, "entry_id")
    path = f"{_space_env_prefix(space_id, environment)}/entries/{quote(entry_id, safe='')}"
    return "GET", path, None, {}, None


def _build_list_entries(
    params: dict[str, Any],
    space_id: str,
    environment: str,
) -> RequestSpec:
    query: dict[str, Any] = {}
    raw_filters = params.get("filters")
    if isinstance(raw_filters, dict):
        for key, value in raw_filters.items():
            if value in (None, ""):
                continue
            query[str(key)] = _stringify(value)
    for key in ("content_type", "limit", "skip", "order"):
        value = params.get(key)
        if value in (None, ""):
            continue
        query_key = "content_type" if key == "content_type" else key
        query[query_key] = _stringify(value)
    path = f"{_space_env_prefix(space_id, environment)}/entries"
    return "GET", path, None, query, None


def _build_create_entry(
    params: dict[str, Any],
    space_id: str,
    environment: str,
) -> RequestSpec:
    content_type = _required(params, "content_type")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Contentful: 'fields' is required and must be a JSON object"
        raise ValueError(msg)
    body: dict[str, Any] = {"fields": fields}
    path = f"{_space_env_prefix(space_id, environment)}/entries"
    query: dict[str, Any] = {"content_type": content_type}
    return "POST", path, body, query, None


def _build_update_entry(
    params: dict[str, Any],
    space_id: str,
    environment: str,
) -> RequestSpec:
    entry_id = _required(params, "entry_id")
    version = _required_int(params, "version")
    fields = params.get("fields")
    if not isinstance(fields, dict) or not fields:
        msg = "Contentful: 'fields' is required and must be a JSON object"
        raise ValueError(msg)
    body: dict[str, Any] = {"fields": fields}
    path = f"{_space_env_prefix(space_id, environment)}/entries/{quote(entry_id, safe='')}"
    return "PUT", path, body, {}, version


def _build_publish_entry(
    params: dict[str, Any],
    space_id: str,
    environment: str,
) -> RequestSpec:
    entry_id = _required(params, "entry_id")
    version = _required_int(params, "version")
    path = (
        f"{_space_env_prefix(space_id, environment)}"
        f"/entries/{quote(entry_id, safe='')}/published"
    )
    return "PUT", path, None, {}, version


def _build_delete_entry(
    params: dict[str, Any],
    space_id: str,
    environment: str,
) -> RequestSpec:
    entry_id = _required(params, "entry_id")
    version = _required_int(params, "version")
    path = f"{_space_env_prefix(space_id, environment)}/entries/{quote(entry_id, safe='')}"
    return "DELETE", path, None, {}, version


def _build_get_asset(
    params: dict[str, Any],
    space_id: str,
    environment: str,
) -> RequestSpec:
    asset_id = _required(params, "asset_id")
    path = f"{_space_env_prefix(space_id, environment)}/assets/{quote(asset_id, safe='')}"
    return "GET", path, None, {}, None


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Contentful: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_int(params: dict[str, Any], key: str) -> int:
    raw: Any = params.get(key)
    if raw in (None, ""):
        msg = f"Contentful: {key!r} is required"
        raise ValueError(msg)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Contentful: {key!r} must be an integer"
        raise ValueError(msg) from exc


_Builder = Callable[[dict[str, Any], str, str], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_ENTRY: _build_get_entry,
    OP_LIST_ENTRIES: _build_list_entries,
    OP_CREATE_ENTRY: _build_create_entry,
    OP_UPDATE_ENTRY: _build_update_entry,
    OP_PUBLISH_ENTRY: _build_publish_entry,
    OP_DELETE_ENTRY: _build_delete_entry,
    OP_GET_ASSET: _build_get_asset,
}
