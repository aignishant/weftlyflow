"""Google Drive node — files, folders, uploads, downloads via Drive v3.

Dispatches to ``https://www.googleapis.com`` with
``Authorization: Bearer <access_token>`` supplied by
:class:`~weftlyflow.credentials.types.google_drive_oauth2.GoogleDriveOAuth2Credential`.

Distinctive Google Drive semantics:

* **``upload_file``** uses ``multipart/related`` — the ``/upload``
  endpoint variant — so metadata (JSON) and file bytes travel in a
  single round-trip separated by a boundary. The node composes the
  envelope itself rather than delegating to ``httpx``'s ``files=``
  kwarg, because Drive expects the specific ``Content-Type:
  application/json`` + bytes-with-caller-declared-mime two-part shape,
  not the default multipart/form-data.
* **``download_file``** is the same endpoint as ``get_file`` but with
  ``?alt=media`` to return bytes rather than the metadata JSON.
* **``create_folder``** is a ``files.create`` call with no payload and
  the Google-specific folder mime-type.

Binary content is carried in/out as base64 in JSON so node results
remain safe to persist through the engine's Item pipeline.

Parameters (all expression-capable):

* ``operation`` — one of six.
* ``file_id`` — target for single-file operations.
* ``name`` / ``mime_type`` / ``parents`` / ``content_base64`` — create/upload.
* ``q`` / ``pageSize`` / ``pageToken`` / ``orderBy`` / ``spaces`` / ``fields`` — list.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` (``content_base64`` on download).
"""

from __future__ import annotations

import base64
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
from weftlyflow.nodes.integrations.google_drive.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    DRIVE_API_BASE,
    OP_CREATE_FOLDER,
    OP_DELETE_FILE,
    OP_DOWNLOAD_FILE,
    OP_GET_FILE,
    OP_LIST_FILES,
    OP_UPLOAD_FILE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.google_drive.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "google_drive_oauth2"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.google_drive_oauth2",)
_FILE_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_FILE, OP_DOWNLOAD_FILE, OP_DELETE_FILE},
)
_LIST_OPERATIONS: frozenset[str] = frozenset({OP_LIST_FILES})
_WRITE_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_FOLDER, OP_UPLOAD_FILE},
)

log = structlog.get_logger(__name__)


class GoogleDriveNode(BaseNode):
    """Dispatch a single Google Drive API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.google_drive",
        version=1,
        display_name="Google Drive",
        description="Manage files and folders on Google Drive via the v3 API.",
        icon="icons/google_drive.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "storage"],
        documentation_url="https://developers.google.com/drive/api/reference/rest/v3",
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
                default=OP_LIST_FILES,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_FILES, label="List Files"),
                    PropertyOption(value=OP_GET_FILE, label="Get File"),
                    PropertyOption(value=OP_CREATE_FOLDER, label="Create Folder"),
                    PropertyOption(value=OP_UPLOAD_FILE, label="Upload File"),
                    PropertyOption(value=OP_DOWNLOAD_FILE, label="Download File"),
                    PropertyOption(value=OP_DELETE_FILE, label="Delete File"),
                ],
            ),
            PropertySchema(
                name="file_id",
                display_name="File ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_FILE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_WRITE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="mime_type",
                display_name="MIME Type",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPLOAD_FILE]},
                ),
            ),
            PropertySchema(
                name="parents",
                display_name="Parent Folder IDs",
                type="json",
                description="Array of parent folder IDs.",
                display_options=DisplayOptions(
                    show={"operation": list(_WRITE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="content_base64",
                display_name="Content (base64)",
                type="string",
                description="File bytes base64-encoded.",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPLOAD_FILE]},
                ),
            ),
            PropertySchema(
                name="q",
                display_name="Query (Drive syntax)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="pageSize",
                display_name="Page Size",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="pageToken",
                display_name="Page Token",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="orderBy",
                display_name="Order By",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields Projection",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_FILES, OP_GET_FILE]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Google Drive API call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=DRIVE_API_BASE, timeout=DEFAULT_TIMEOUT_SECONDS,
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
        msg = "Google Drive: a google_drive_oauth2 credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("access_token") or "").strip():
        msg = "Google Drive: credential has an empty 'access_token'"
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
    operation = str(params.get("operation") or OP_LIST_FILES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Google Drive: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query, content_type = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = _build_request(
        client,
        method=method,
        path=path,
        body=body,
        query=query,
        content_type=content_type,
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("google_drive.request_failed", operation=operation, error=str(exc))
        msg = f"Google Drive: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _parse_response(response, operation)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "google_drive.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = (
            f"Google Drive {operation} failed "
            f"(HTTP {response.status_code}): {error}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("google_drive.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _build_request(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    body: Any,
    query: dict[str, Any],
    content_type: str | None,
) -> httpx.Request:
    headers: dict[str, str] = {"Accept": "application/json"}
    if isinstance(body, (bytes, bytearray)):
        if content_type:
            headers["Content-Type"] = content_type
        return client.build_request(
            method, path, params=query or None, content=bytes(body), headers=headers,
        )
    if isinstance(body, dict):
        headers["Content-Type"] = "application/json"
        return client.build_request(
            method, path, params=query or None, json=body, headers=headers,
        )
    return client.build_request(
        method, path, params=query or None, headers=headers,
    )


def _parse_response(response: httpx.Response, operation: str) -> Any:
    if operation == OP_DOWNLOAD_FILE and response.status_code < httpx.codes.BAD_REQUEST:
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
