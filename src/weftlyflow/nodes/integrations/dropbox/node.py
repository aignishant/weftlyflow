"""Dropbox node — file/folder operations with split RPC/content endpoints.

Dispatches RPC operations to ``api.dropboxapi.com`` and content
operations (download) to ``content.dropboxapi.com``. Both endpoints
share a Bearer token sourced from
:class:`~weftlyflow.credentials.types.dropbox_api.DropboxApiCredential`,
but content operations carry their argument blob in a
``Dropbox-API-Arg`` header whose value is a JSON-encoded string. That
JSON-in-header shape is distinctive to Dropbox's HTTP surface.

Parameters (all expression-capable):

* ``operation`` — one of the eight file/folder operations.
* ``path`` — Dropbox path (must start with ``/``, ``id:``, or
  ``rev:``); target for most ops.
* ``from_path`` / ``to_path`` — move/copy arguments.
* ``query`` / ``limit`` — search inputs.
* ``recursive`` / ``autorename`` / ``allow_shared_folder`` — optional
  behavioural flags.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` (or, for download, the ``Dropbox-API-Result`` header
plus the raw content length).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

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
from weftlyflow.nodes.integrations.dropbox.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_COPY,
    OP_CREATE_FOLDER,
    OP_DELETE,
    OP_DOWNLOAD,
    OP_GET_METADATA,
    OP_LIST_FOLDER,
    OP_MOVE,
    OP_SEARCH,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.dropbox.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "dropbox_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.dropbox_api",)
_PATH_OPERATIONS: frozenset[str] = frozenset(
    {
        OP_LIST_FOLDER,
        OP_GET_METADATA,
        OP_CREATE_FOLDER,
        OP_DELETE,
        OP_DOWNLOAD,
    },
)
_MOVE_COPY_OPERATIONS: frozenset[str] = frozenset({OP_MOVE, OP_COPY})

log = structlog.get_logger(__name__)


class DropboxNode(BaseNode):
    """Dispatch a single Dropbox call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.dropbox",
        version=1,
        display_name="Dropbox",
        description="Manage Dropbox files and folders.",
        icon="icons/dropbox.svg",
        category=NodeCategory.INTEGRATION,
        group=["files", "storage"],
        documentation_url=(
            "https://www.dropbox.com/developers/documentation/http/documentation"
        ),
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
                default=OP_LIST_FOLDER,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_FOLDER, label="List Folder"),
                    PropertyOption(value=OP_GET_METADATA, label="Get Metadata"),
                    PropertyOption(value=OP_CREATE_FOLDER, label="Create Folder"),
                    PropertyOption(value=OP_DELETE, label="Delete"),
                    PropertyOption(value=OP_MOVE, label="Move"),
                    PropertyOption(value=OP_COPY, label="Copy"),
                    PropertyOption(value=OP_SEARCH, label="Search"),
                    PropertyOption(value=OP_DOWNLOAD, label="Download"),
                ],
            ),
            PropertySchema(
                name="path",
                display_name="Path",
                type="string",
                description="Dropbox path starting with '/', 'id:', or 'rev:'.",
                display_options=DisplayOptions(
                    show={"operation": [*_PATH_OPERATIONS, OP_SEARCH]},
                ),
            ),
            PropertySchema(
                name="from_path",
                display_name="From Path",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_MOVE_COPY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="to_path",
                display_name="To Path",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_MOVE_COPY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="recursive",
                display_name="Recursive",
                type="boolean",
                display_options=DisplayOptions(show={"operation": [OP_LIST_FOLDER]}),
            ),
            PropertySchema(
                name="autorename",
                display_name="Auto-rename",
                type="boolean",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_CREATE_FOLDER,
                            OP_MOVE,
                            OP_COPY,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="allow_shared_folder",
                display_name="Allow Shared Folder",
                type="boolean",
                display_options=DisplayOptions(show={"operation": [OP_MOVE]}),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Dropbox call per input item."""
        access_token = await _resolve_credential(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        access_token=access_token,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credential(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Dropbox: a dropbox_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Dropbox: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    access_token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_FOLDER).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Dropbox: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        base_url, path, body, arg_header = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}
    request_kwargs: dict[str, Any] = {"headers": headers}
    if arg_header is not None:
        headers["Dropbox-API-Arg"] = arg_header
    else:
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        request_kwargs["json"] = body
    try:
        response = await client.post(f"{base_url}{path}", **request_kwargs)
    except httpx.HTTPError as exc:
        logger.error("dropbox.request_failed", operation=operation, error=str(exc))
        msg = f"Dropbox: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    result = _collect_result(operation, response)
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(result.get("response"), response.status_code)
        logger.warning(
            "dropbox.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Dropbox {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("dropbox.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _collect_result(operation: str, response: httpx.Response) -> dict[str, Any]:
    if operation == OP_DOWNLOAD:
        api_result = response.headers.get("Dropbox-API-Result")
        metadata = _parse_header_json(api_result)
        return {
            "operation": operation,
            "status": response.status_code,
            "response": metadata,
            "content_length": len(response.content),
        }
    return {
        "operation": operation,
        "status": response.status_code,
        "response": _safe_json(response),
    }


def _parse_header_json(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except ValueError:
        return {"raw": value}


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        error_summary = payload.get("error_summary")
        if isinstance(error_summary, str) and error_summary:
            return error_summary
        error = payload.get("error")
        if isinstance(error, dict):
            tag = error.get(".tag")
            if isinstance(tag, str) and tag:
                return tag
        if isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"
