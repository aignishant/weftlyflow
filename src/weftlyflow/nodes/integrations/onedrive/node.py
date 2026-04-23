"""OneDrive node — files and folders via Microsoft Graph ``/me/drive``.

Dispatches against ``https://graph.microsoft.com/v1.0`` with
``Authorization: Bearer <access_token>`` supplied by the shared
:class:`~weftlyflow.credentials.types.microsoft_graph.MicrosoftGraphCredential`.

Distinctive OneDrive semantics:

* **``upload_small``** PUTs the raw file bytes (decoded from the
  ``content_base64`` parameter) directly to
  ``/me/drive/root:/{path}:/content`` — no JSON envelope, no multipart
  framing. Content-Type defaults to ``application/octet-stream``.
* **``upload_large``** is a *two-step session-based* resumable upload
  unique among nodes in the catalog:

  1. POST to ``/me/drive/root:/{path}:/createUploadSession`` returns an
     ``uploadUrl`` (short-lived, unauthenticated, outside the Graph
     host).
  2. The node then PUTs successive byte ranges (default ~3.2 MiB —
     Graph requires a multiple of 320 KiB) to that URL with
     ``Content-Range: bytes START-END/TOTAL`` and ``Content-Length`` on
     each chunk. Intermediate chunks return HTTP 202; the final chunk
     returns the ``driveItem`` JSON.

  Crucially, the chunk PUTs **must not** carry the Graph Authorization
  header (the uploadUrl is pre-signed), so those requests are issued
  through a fresh ``httpx.AsyncClient`` with no base_url and no
  credential injector.

* **``download_item``** returns the raw bytes base64-encoded inside the
  response payload so node results stay persistable through the Item
  pipeline.

Parameters (all expression-capable):

* ``operation`` — one of six.
* ``file_path`` / ``item_id`` — address items by path or by Graph id.
* ``folder_path`` — ``list_children``; empty means drive root.
* ``content_base64`` — upload bytes (base64).
* ``conflict_behavior`` — ``replace`` | ``rename`` | ``fail``.
* ``chunk_size_bytes`` — chunk size override for ``upload_large`` (must
  be a multiple of 320 KiB).
* ``$top`` / ``$skip`` / ``$orderby`` / ``$select`` / ``$filter`` — list.

Output: one item per input item with ``operation``, ``status`` and the
parsed ``response`` (``content_base64`` on download, ``driveItem`` JSON
on upload).
"""

from __future__ import annotations

import base64
import binascii
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
from weftlyflow.nodes.integrations.onedrive.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_UPLOAD_CHUNK_BYTES,
    GRAPH_API_BASE,
    OP_DELETE_ITEM,
    OP_DOWNLOAD_ITEM,
    OP_GET_ITEM,
    OP_LIST_CHILDREN,
    OP_UPLOAD_LARGE,
    OP_UPLOAD_SMALL,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.onedrive.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "microsoft_graph"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.microsoft_graph",)
_CHUNK_ALIGNMENT_BYTES: int = 320 * 1024
_PATH_OPERATIONS: frozenset[str] = frozenset(
    {OP_UPLOAD_SMALL, OP_UPLOAD_LARGE},
)
_ITEM_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_ITEM, OP_DOWNLOAD_ITEM, OP_DELETE_ITEM},
)
_UPLOAD_OPERATIONS: frozenset[str] = frozenset(
    {OP_UPLOAD_SMALL, OP_UPLOAD_LARGE},
)

log = structlog.get_logger(__name__)


class OneDriveNode(BaseNode):
    """Dispatch a single OneDrive Graph API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.onedrive",
        version=1,
        display_name="OneDrive",
        description="Manage OneDrive files and folders via Microsoft Graph.",
        icon="icons/onedrive.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "storage"],
        documentation_url="https://learn.microsoft.com/en-us/graph/api/resources/onedrive",
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
                default=OP_LIST_CHILDREN,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_CHILDREN, label="List Children"),
                    PropertyOption(value=OP_GET_ITEM, label="Get Item"),
                    PropertyOption(value=OP_UPLOAD_SMALL, label="Upload Small (<4 MiB)"),
                    PropertyOption(value=OP_UPLOAD_LARGE, label="Upload Large (session)"),
                    PropertyOption(value=OP_DOWNLOAD_ITEM, label="Download Item"),
                    PropertyOption(value=OP_DELETE_ITEM, label="Delete Item"),
                ],
            ),
            PropertySchema(
                name="folder_path",
                display_name="Folder Path",
                type="string",
                description="Drive-root-relative path; empty means drive root.",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHILDREN]},
                ),
            ),
            PropertySchema(
                name="file_path",
                display_name="File Path",
                type="string",
                description="Drive-root-relative path for upload ops.",
                display_options=DisplayOptions(
                    show={"operation": list(_PATH_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="item_id",
                display_name="Item ID",
                type="string",
                description="Graph driveItem id (overrides file_path when set).",
                display_options=DisplayOptions(
                    show={"operation": list(_ITEM_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="content_base64",
                display_name="Content (base64)",
                type="string",
                description="File bytes base64-encoded.",
                display_options=DisplayOptions(
                    show={"operation": list(_UPLOAD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="conflict_behavior",
                display_name="Conflict Behavior",
                type="options",
                default="replace",
                options=[
                    PropertyOption(value="replace", label="Replace"),
                    PropertyOption(value="rename", label="Rename"),
                    PropertyOption(value="fail", label="Fail"),
                ],
                display_options=DisplayOptions(
                    show={"operation": list(_UPLOAD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="chunk_size_bytes",
                display_name="Chunk Size (bytes)",
                type="number",
                default=DEFAULT_UPLOAD_CHUNK_BYTES,
                description="Upload chunk size; must be a multiple of 320 KiB.",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPLOAD_LARGE]},
                ),
            ),
            PropertySchema(
                name="$top",
                display_name="Top",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHILDREN]},
                ),
            ),
            PropertySchema(
                name="$skip",
                display_name="Skip",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHILDREN]},
                ),
            ),
            PropertySchema(
                name="$orderby",
                display_name="Order By",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHILDREN]},
                ),
            ),
            PropertySchema(
                name="$select",
                display_name="Select",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHILDREN]},
                ),
            ),
            PropertySchema(
                name="$filter",
                display_name="Filter",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_CHILDREN]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one OneDrive Graph API call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=GRAPH_API_BASE, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        injector=injector,
                        creds=payload,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "OneDrive: a microsoft_graph credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("access_token") or "").strip():
        msg = "OneDrive: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_CHILDREN).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"OneDrive: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if operation == OP_UPLOAD_SMALL:
        return await _run_upload_small(
            ctx, params, client=client, injector=injector,
            creds=creds, logger=logger,
        )
    if operation == OP_UPLOAD_LARGE:
        return await _run_upload_large(
            ctx, params, client=client, injector=injector,
            creds=creds, logger=logger,
        )
    return await _run_simple(
        ctx, operation, params,
        client=client, injector=injector, creds=creds, logger=logger,
    )


async def _run_simple(
    ctx: ExecutionContext,
    operation: str,
    params: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = _build_json_request(
        client, method=method, path=path, body=body, query=query,
    )
    request = await injector.inject(creds, request)
    response = await _send(client, request, operation, ctx, logger)
    payload = _parse_response(response, operation)
    return _wrap_result(ctx, operation, response, payload, logger)


async def _run_upload_small(
    ctx: ExecutionContext,
    params: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    content = _decode_content(ctx, params)
    try:
        method, path, _body, query = build_request(OP_UPLOAD_SMALL, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers = {"Content-Type": "application/octet-stream", "Accept": "application/json"}
    request = client.build_request(
        method, path, params=query or None, content=content, headers=headers,
    )
    request = await injector.inject(creds, request)
    response = await _send(client, request, OP_UPLOAD_SMALL, ctx, logger)
    payload = _parse_response(response, OP_UPLOAD_SMALL)
    return _wrap_result(ctx, OP_UPLOAD_SMALL, response, payload, logger)


async def _run_upload_large(
    ctx: ExecutionContext,
    params: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    content = _decode_content(ctx, params)
    chunk_size = _resolve_chunk_size(ctx, params)
    try:
        method, path, body, query = build_request(OP_UPLOAD_LARGE, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    session_request = _build_json_request(
        client, method=method, path=path, body=body, query=query,
    )
    session_request = await injector.inject(creds, session_request)
    session_response = await _send(
        client, session_request, OP_UPLOAD_LARGE, ctx, logger,
    )
    session_payload = _parse_response(session_response, OP_UPLOAD_LARGE)
    if session_response.status_code >= httpx.codes.BAD_REQUEST:
        _raise_api_error(ctx, OP_UPLOAD_LARGE, session_response, session_payload, logger)
    upload_url = _require_upload_url(ctx, session_payload)
    final_response, final_payload = await _stream_chunks(
        ctx, upload_url=upload_url, content=content,
        chunk_size=chunk_size, logger=logger,
    )
    return _wrap_result(ctx, OP_UPLOAD_LARGE, final_response, final_payload, logger)


async def _stream_chunks(
    ctx: ExecutionContext,
    *,
    upload_url: str,
    content: bytes,
    chunk_size: int,
    logger: Any,
) -> tuple[httpx.Response, Any]:
    total = len(content)
    if total == 0:
        msg = "OneDrive: upload_large content is empty"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as chunk_client:
        offset = 0
        response: httpx.Response | None = None
        while offset < total:
            end = min(offset + chunk_size, total) - 1
            chunk = content[offset : end + 1]
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{end}/{total}",
            }
            try:
                response = await chunk_client.put(
                    upload_url, content=chunk, headers=headers,
                )
            except httpx.HTTPError as exc:
                logger.error(
                    "onedrive.chunk_failed",
                    operation=OP_UPLOAD_LARGE,
                    offset=offset,
                    error=str(exc),
                )
                msg = f"OneDrive: chunk upload failed at offset {offset}: {exc}"
                raise NodeExecutionError(
                    msg, node_id=ctx.node.id, original=exc,
                ) from exc
            if response.status_code >= httpx.codes.BAD_REQUEST:
                payload = _parse_response(response, OP_UPLOAD_LARGE)
                _raise_api_error(ctx, OP_UPLOAD_LARGE, response, payload, logger)
            offset = end + 1
    if response is None:
        msg = "OneDrive: upload_large produced no response"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return response, _parse_response(response, OP_UPLOAD_LARGE)


def _build_json_request(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    query: dict[str, Any],
) -> httpx.Request:
    headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
        return client.build_request(
            method, path, params=query or None, json=body, headers=headers,
        )
    return client.build_request(
        method, path, params=query or None, headers=headers,
    )


async def _send(
    client: httpx.AsyncClient,
    request: httpx.Request,
    operation: str,
    ctx: ExecutionContext,
    logger: Any,
) -> httpx.Response:
    try:
        return await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("onedrive.request_failed", operation=operation, error=str(exc))
        msg = f"OneDrive: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc


def _wrap_result(
    ctx: ExecutionContext,
    operation: str,
    response: httpx.Response,
    payload: Any,
    logger: Any,
) -> Item:
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        _raise_api_error(ctx, operation, response, payload, logger)
    logger.info("onedrive.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _raise_api_error(
    ctx: ExecutionContext,
    operation: str,
    response: httpx.Response,
    payload: Any,
    logger: Any,
) -> None:
    error = _error_message(payload, response.status_code)
    logger.warning(
        "onedrive.api_error",
        operation=operation,
        status=response.status_code,
        error=error,
    )
    msg = f"OneDrive {operation} failed (HTTP {response.status_code}): {error}"
    raise NodeExecutionError(msg, node_id=ctx.node.id)


def _parse_response(response: httpx.Response, operation: str) -> Any:
    if operation == OP_DOWNLOAD_ITEM and response.status_code < httpx.codes.BAD_REQUEST:
        return {
            "content_base64": base64.b64encode(response.content).decode("ascii"),
            "content_type": response.headers.get("Content-Type", ""),
            "content_length": len(response.content),
        }
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
        if isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"


def _decode_content(ctx: ExecutionContext, params: dict[str, Any]) -> bytes:
    encoded = str(params.get("content_base64") or "").strip()
    if not encoded:
        msg = "OneDrive: 'content_base64' is required for upload operations"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        msg = "OneDrive: 'content_base64' is not valid base64"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc


def _resolve_chunk_size(ctx: ExecutionContext, params: dict[str, Any]) -> int:
    raw = params.get("chunk_size_bytes")
    if raw in (None, ""):
        return DEFAULT_UPLOAD_CHUNK_BYTES
    try:
        size = int(str(raw))
    except (TypeError, ValueError) as exc:
        msg = f"OneDrive: 'chunk_size_bytes' must be an integer, got {raw!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    if size <= 0 or size % _CHUNK_ALIGNMENT_BYTES != 0:
        msg = (
            "OneDrive: 'chunk_size_bytes' must be a positive multiple of "
            f"{_CHUNK_ALIGNMENT_BYTES} (320 KiB)"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return size


def _require_upload_url(ctx: ExecutionContext, payload: Any) -> str:
    if isinstance(payload, dict):
        url = payload.get("uploadUrl")
        if isinstance(url, str) and url:
            return url
    msg = "OneDrive: createUploadSession response missing 'uploadUrl'"
    raise NodeExecutionError(msg, node_id=ctx.node.id)
