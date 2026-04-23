"""Box node — folder/file lifecycle + search over the Content API v2.0.

Dispatches to ``api.box.com/2.0`` with ``Authorization: Bearer
<access_token>`` sourced from
:class:`~weftlyflow.credentials.types.box_api.BoxApiCredential`.

The distinctive shape here is the credential-owned ``As-User`` header.
Enterprise admins and JWT-server-auth apps can impersonate a managed
user for the scope of a request by setting that header — carrying the
impersonation target on the credential keeps every call in the
workflow acting as the same user without per-node configuration.

Parameters (all expression-capable):

* ``operation`` — ``list_folder``, ``get_file``, ``delete_file``,
  ``create_folder``, ``copy_file``, ``search``, ``list_users``.
* ``folder_id`` / ``file_id`` — target resource (``0`` = root).
* ``name`` / ``parent_id`` / ``new_name`` — create / copy targets.
* ``query`` / ``content_types`` / ``ancestor_folder_ids`` /
  ``file_extensions`` — search filters.
* ``limit`` / ``offset`` / ``fields`` — paging + projection.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

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
from weftlyflow.nodes.integrations.box.constants import (
    API_BASE_URL,
    AS_USER_HEADER,
    DEFAULT_TIMEOUT_SECONDS,
    OP_COPY_FILE,
    OP_CREATE_FOLDER,
    OP_DELETE_FILE,
    OP_GET_FILE,
    OP_LIST_FOLDER,
    OP_LIST_USERS,
    OP_SEARCH,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.box.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "box_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.box_api",)
_FILE_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_FILE, OP_DELETE_FILE, OP_COPY_FILE},
)
_FIELDS_OPERATIONS: frozenset[str] = frozenset({OP_LIST_FOLDER, OP_GET_FILE})
_PAGED_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_FOLDER, OP_SEARCH, OP_LIST_USERS},
)

log = structlog.get_logger(__name__)


class BoxNode(BaseNode):
    """Dispatch a single Box Content REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.box",
        version=1,
        display_name="Box",
        description="Manage Box folders, files, and enterprise users.",
        icon="icons/box.svg",
        category=NodeCategory.INTEGRATION,
        group=["storage", "collaboration"],
        documentation_url="https://developer.box.com/reference/",
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
                    PropertyOption(value=OP_GET_FILE, label="Get File"),
                    PropertyOption(value=OP_DELETE_FILE, label="Delete File"),
                    PropertyOption(value=OP_CREATE_FOLDER, label="Create Folder"),
                    PropertyOption(value=OP_COPY_FILE, label="Copy File"),
                    PropertyOption(value=OP_SEARCH, label="Search"),
                    PropertyOption(value=OP_LIST_USERS, label="List Users"),
                ],
            ),
            PropertySchema(
                name="folder_id",
                display_name="Folder ID",
                type="string",
                default="0",
                description="Box folder ID ('0' = root).",
                display_options=DisplayOptions(show={"operation": [OP_LIST_FOLDER]}),
            ),
            PropertySchema(
                name="file_id",
                display_name="File ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_FILE_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_FOLDER]}),
            ),
            PropertySchema(
                name="parent_id",
                display_name="Parent Folder ID",
                type="string",
                default="0",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_FOLDER, OP_COPY_FILE]},
                ),
            ),
            PropertySchema(
                name="new_name",
                display_name="New Name",
                type="string",
                description="Rename the copy (optional).",
                display_options=DisplayOptions(show={"operation": [OP_COPY_FILE]}),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="content_types",
                display_name="Content Types",
                type="string",
                description="Comma-separated (name,description,comments,tags).",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="ancestor_folder_ids",
                display_name="Ancestor Folder IDs",
                type="string",
                description="Comma-separated folder-ID allowlist.",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="file_extensions",
                display_name="File Extensions",
                type="string",
                description="Comma-separated extensions (no leading dot).",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH]}),
            ),
            PropertySchema(
                name="filter_term",
                display_name="Filter Term",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_USERS]}),
            ),
            PropertySchema(
                name="user_type",
                display_name="User Type",
                type="string",
                description="all, managed, or external.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_USERS]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="string",
                description="Comma-separated projection.",
                display_options=DisplayOptions(
                    show={"operation": list(_FIELDS_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_PAGED_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_FOLDER]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Box REST call per input item."""
        access_token, as_user = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if as_user:
            headers[AS_USER_HEADER] = as_user
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        headers=headers,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Box: a box_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Box: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, str(payload.get("as_user_id") or "").strip()


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_FOLDER).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Box: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers = dict(headers)
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers=request_headers,
        )
    except httpx.HTTPError as exc:
        logger.error("box.request_failed", operation=operation, error=str(exc))
        msg = f"Box: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "box.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Box {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("box.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        code = payload.get("code")
        message = payload.get("message")
        if isinstance(code, str) and isinstance(message, str):
            return f"{code}: {message}"
        if isinstance(message, str) and message:
            return message
        context_info = payload.get("context_info")
        if isinstance(context_info, dict):
            errors = context_info.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    reason = first.get("reason")
                    if isinstance(reason, str) and reason:
                        return reason
    return f"HTTP {status_code}"
