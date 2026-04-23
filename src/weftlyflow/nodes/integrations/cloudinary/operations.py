"""Per-operation request builders for the Cloudinary node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://api.cloudinary.com`` and always begin with
``/v1_1/{cloud_name}/...``. Upload and destroy produce form bodies
that the node post-processes with
:func:`~weftlyflow.credentials.types.cloudinary_api.sign_params`
before dispatch; admin listings return an empty body and the node
relies on the credential's Basic auth header.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.cloudinary.constants import (
    OP_DESTROY,
    OP_GET_RESOURCE,
    OP_LIST_RESOURCES,
    OP_UPLOAD,
    RESOURCE_IMAGE,
    SUPPORTED_RESOURCE_TYPES,
)

RequestSpec = tuple[str, str, dict[str, Any], dict[str, str]]


def build_request(
    operation: str, cloud_name: str, params: dict[str, Any],
) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    if not cloud_name.strip():
        msg = "Cloudinary: cloud_name is required"
        raise ValueError(msg)
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Cloudinary: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(cloud_name.strip(), params)


def _resource_type(params: dict[str, Any]) -> str:
    resource = str(params.get("resource_type") or RESOURCE_IMAGE).strip().lower()
    if resource not in SUPPORTED_RESOURCE_TYPES:
        msg = (
            f"Cloudinary: 'resource_type' must be one of "
            f"{list(SUPPORTED_RESOURCE_TYPES)!r} — got {resource!r}"
        )
        raise ValueError(msg)
    return resource


def _build_upload(cloud_name: str, params: dict[str, Any]) -> RequestSpec:
    resource = _resource_type(params)
    file_ref = _required_str(params, "file")
    body: dict[str, Any] = {"file": file_ref}
    public_id = str(params.get("public_id") or "").strip()
    if public_id:
        body["public_id"] = public_id
    folder = str(params.get("folder") or "").strip()
    if folder:
        body["folder"] = folder
    tags = params.get("tags")
    if isinstance(tags, list) and tags:
        body["tags"] = ",".join(str(tag) for tag in tags)
    elif isinstance(tags, str) and tags.strip():
        body["tags"] = tags.strip()
    context = params.get("context")
    if isinstance(context, dict) and context:
        body["context"] = "|".join(f"{k}={v}" for k, v in context.items())
    elif isinstance(context, str) and context.strip():
        body["context"] = context.strip()
    return "POST", f"/v1_1/{cloud_name}/{resource}/upload", body, {}


def _build_destroy(cloud_name: str, params: dict[str, Any]) -> RequestSpec:
    resource = _resource_type(params)
    public_id = _required_str(params, "public_id")
    body: dict[str, Any] = {"public_id": public_id}
    invalidate = params.get("invalidate")
    if isinstance(invalidate, bool) and invalidate:
        body["invalidate"] = "true"
    return "POST", f"/v1_1/{cloud_name}/{resource}/destroy", body, {}


def _build_list_resources(cloud_name: str, params: dict[str, Any]) -> RequestSpec:
    resource = _resource_type(params)
    query: dict[str, str] = {}
    max_results = str(params.get("max_results") or "").strip()
    if max_results:
        query["max_results"] = max_results
    prefix = str(params.get("prefix") or "").strip()
    if prefix:
        query["prefix"] = prefix
    next_cursor = str(params.get("next_cursor") or "").strip()
    if next_cursor:
        query["next_cursor"] = next_cursor
    return "GET", f"/v1_1/{cloud_name}/resources/{resource}", {}, query


def _build_get_resource(cloud_name: str, params: dict[str, Any]) -> RequestSpec:
    resource = _resource_type(params)
    public_id = _required_str(params, "public_id")
    delivery_type = str(params.get("delivery_type") or "upload").strip()
    return (
        "GET",
        f"/v1_1/{cloud_name}/resources/{resource}/{delivery_type}/{public_id}",
        {},
        {},
    )


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Cloudinary: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[str, dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_UPLOAD: _build_upload,
    OP_DESTROY: _build_destroy,
    OP_LIST_RESOURCES: _build_list_resources,
    OP_GET_RESOURCE: _build_get_resource,
}
