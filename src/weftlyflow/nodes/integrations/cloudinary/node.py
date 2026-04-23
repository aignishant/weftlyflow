"""Cloudinary node — media uploads, destroys, and resource listings.

Dispatches against ``https://api.cloudinary.com``. The credential
injects HTTP Basic auth that covers the admin read endpoints
(list_resources, get_resource); for upload and destroy, the node
additionally stamps ``api_key`` + ``timestamp`` + ``signature`` into
the form body, where the signature is the SHA-1 of the sorted
``key=value`` pairs concatenated directly with ``api_secret``.

Parameters (all expression-capable):

* ``operation``      — ``upload`` / ``destroy`` / ``list_resources`` /
  ``get_resource``.
* ``resource_type``  — ``image`` (default) / ``video`` / ``raw``.
* ``file``           — required for upload. Remote URL, data URI, or
  Cloudinary ``cloudinary://`` reference.
* ``public_id``      — required for destroy and get_resource; optional
  for upload to force a specific ID.
* ``folder`` / ``tags`` / ``context`` — optional upload metadata.
* ``invalidate``     — boolean, forces CDN purge on destroy.
* ``delivery_type``  — ``upload`` (default) / ``fetch`` / ``private``
  for get_resource.
* ``max_results`` / ``prefix`` / ``next_cursor`` — list_resources
  pagination and filtering.

Output: one item per input item with ``operation``, ``status``, and
parsed ``response``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.cloudinary_api import sign_params
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    DisplayOptions,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.integrations.cloudinary.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_DESTROY,
    OP_GET_RESOURCE,
    OP_LIST_RESOURCES,
    OP_UPLOAD,
    RESOURCE_IMAGE,
    RESOURCE_RAW,
    RESOURCE_VIDEO,
    SIGNED_OPERATIONS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.cloudinary.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_API_BASE_URL: str = "https://api.cloudinary.com"
_CREDENTIAL_SLOT: str = "cloudinary_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.cloudinary_api",)

log = structlog.get_logger(__name__)


class CloudinaryNode(BaseNode):
    """Dispatch a single Cloudinary call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.cloudinary",
        version=1,
        display_name="Cloudinary",
        description="Upload, destroy, and list Cloudinary media resources.",
        icon="icons/cloudinary.svg",
        category=NodeCategory.INTEGRATION,
        group=["media"],
        documentation_url="https://cloudinary.com/documentation/admin_api",
        credentials=[
            CredentialSlot(
                name=_CREDENTIAL_SLOT,
                required=True,
                credential_types=list(_CREDENTIAL_SLUGS),
            ),
        ],
        properties=[
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=OP_UPLOAD,
                required=True,
                options=[
                    PropertyOption(value=OP_UPLOAD, label="Upload"),
                    PropertyOption(value=OP_DESTROY, label="Destroy"),
                    PropertyOption(value=OP_LIST_RESOURCES, label="List Resources"),
                    PropertyOption(value=OP_GET_RESOURCE, label="Get Resource"),
                ],
            ),
            PropertySchema(
                name="resource_type",
                display_name="Resource Type",
                type="options",
                default=RESOURCE_IMAGE,
                options=[
                    PropertyOption(value=RESOURCE_IMAGE, label="Image"),
                    PropertyOption(value=RESOURCE_VIDEO, label="Video"),
                    PropertyOption(value=RESOURCE_RAW, label="Raw"),
                ],
            ),
            PropertySchema(
                name="file",
                display_name="File",
                type="string",
                description="Remote URL, data URI, or cloudinary:// reference.",
                display_options=DisplayOptions(show={"operation": [OP_UPLOAD]}),
            ),
            PropertySchema(
                name="public_id",
                display_name="Public ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPLOAD, OP_DESTROY, OP_GET_RESOURCE]},
                ),
            ),
            PropertySchema(
                name="folder",
                display_name="Folder",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_UPLOAD]}),
            ),
            PropertySchema(
                name="tags",
                display_name="Tags",
                type="string",
                description="Comma-separated tag list.",
                display_options=DisplayOptions(show={"operation": [OP_UPLOAD]}),
            ),
            PropertySchema(
                name="context",
                display_name="Context",
                type="json",
                description='Key/value metadata, e.g. {"alt": "logo"}.',
                display_options=DisplayOptions(show={"operation": [OP_UPLOAD]}),
            ),
            PropertySchema(
                name="invalidate",
                display_name="Invalidate CDN",
                type="boolean",
                default=False,
                display_options=DisplayOptions(show={"operation": [OP_DESTROY]}),
            ),
            PropertySchema(
                name="delivery_type",
                display_name="Delivery Type",
                type="string",
                default="upload",
                description="upload / fetch / private / authenticated.",
                display_options=DisplayOptions(show={"operation": [OP_GET_RESOURCE]}),
            ),
            PropertySchema(
                name="max_results",
                display_name="Max Results",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RESOURCES]}),
            ),
            PropertySchema(
                name="prefix",
                display_name="Prefix",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RESOURCES]}),
            ),
            PropertySchema(
                name="next_cursor",
                display_name="Next Cursor",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RESOURCES]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Cloudinary call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        cloud_name = str(payload.get("cloud_name") or "").strip()
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        seed = items or [Item()]
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=_API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item,
                        client=client, injector=injector,
                        creds=payload, cloud_name=cloud_name, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Cloudinary: a cloudinary_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    for key in ("cloud_name", "api_key", "api_secret"):
        if not str(payload.get(key) or "").strip():
            msg = f"Cloudinary: credential has an empty {key!r}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    cloud_name: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_UPLOAD).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Cloudinary: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, cloud_name, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    if operation in SIGNED_OPERATIONS:
        _sign_body(body, creds)
    form_data = body if method == "POST" else None
    request = client.build_request(
        method, path,
        params=query or None,
        data=form_data,
        headers={"Accept": "application/json"},
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("cloudinary.request_failed", operation=operation, error=str(exc))
        msg = f"Cloudinary: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    parsed = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": parsed,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(parsed, response.status_code)
        logger.warning(
            "cloudinary.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Cloudinary {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("cloudinary.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _sign_body(body: dict[str, Any], creds: dict[str, Any]) -> None:
    body["timestamp"] = str(int(time.time()))
    body["api_key"] = str(creds.get("api_key", "")).strip()
    body["signature"] = sign_params(body, str(creds.get("api_secret", "")).strip())


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
        for key in ("message", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
