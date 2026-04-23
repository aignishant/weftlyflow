"""Asana node — tasks + stories lifecycle over the v1.0 API.

Dispatches to ``app.asana.com/api/1.0`` with ``Authorization: Bearer
<access_token>`` sourced from
:class:`~weftlyflow.credentials.types.asana_api.AsanaApiCredential`.

The distinctive shape here is the credential-owned ``Asana-Enable``
opt-in header — a comma-separated list of feature flags that toggle
beta behaviours or deprecations on the caller's tenant. When present
on the credential, the node echoes it on every request so the API
version contract is stable across operations.

Asana wraps request and response bodies in a top-level ``data`` key;
the operation builders add that envelope on the request side.

Parameters (all expression-capable):

* ``operation`` — ``list_tasks``, ``get_task``, ``create_task``,
  ``update_task``, ``delete_task``, ``add_comment``.
* ``task_id`` — target task (gid).
* ``project`` / ``assignee`` / ``workspace`` / ``completed_since`` /
  ``limit`` / ``offset`` / ``opt_fields`` — list paging + projection.
* ``document`` — task payload for create/update.
* ``text`` / ``html_text`` / ``is_pinned`` — add_comment inputs.

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
from weftlyflow.nodes.integrations.asana.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    ENABLE_HEADER,
    OP_ADD_COMMENT,
    OP_CREATE_TASK,
    OP_DELETE_TASK,
    OP_GET_TASK,
    OP_LIST_TASKS,
    OP_UPDATE_TASK,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.asana.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "asana_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.asana_api",)
_TASK_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_TASK, OP_UPDATE_TASK, OP_DELETE_TASK, OP_ADD_COMMENT},
)
_DOCUMENT_OPERATIONS: frozenset[str] = frozenset({OP_CREATE_TASK, OP_UPDATE_TASK})
_OPT_FIELD_OPERATIONS: frozenset[str] = frozenset({OP_LIST_TASKS, OP_GET_TASK})

log = structlog.get_logger(__name__)


class AsanaNode(BaseNode):
    """Dispatch a single Asana REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.asana",
        version=1,
        display_name="Asana",
        description="Manage Asana tasks, projects, and comments.",
        icon="icons/asana.svg",
        category=NodeCategory.INTEGRATION,
        group=["project-management", "collaboration"],
        documentation_url="https://developers.asana.com/reference",
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
                default=OP_LIST_TASKS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_TASKS, label="List Tasks"),
                    PropertyOption(value=OP_GET_TASK, label="Get Task"),
                    PropertyOption(value=OP_CREATE_TASK, label="Create Task"),
                    PropertyOption(value=OP_UPDATE_TASK, label="Update Task"),
                    PropertyOption(value=OP_DELETE_TASK, label="Delete Task"),
                    PropertyOption(value=OP_ADD_COMMENT, label="Add Comment"),
                ],
            ),
            PropertySchema(
                name="task_id",
                display_name="Task GID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_TASK_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="project",
                display_name="Project",
                type="string",
                description="Project GID (pairs with workspace scope).",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="assignee",
                display_name="Assignee",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="workspace",
                display_name="Workspace",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="completed_since",
                display_name="Completed Since",
                type="string",
                description="ISO 8601 (or 'now' for open tasks only).",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset Token",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="opt_fields",
                display_name="Opt Fields",
                type="string",
                description="Comma-separated $opt_fields projection.",
                display_options=DisplayOptions(
                    show={"operation": list(_OPT_FIELD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="document",
                display_name="Task Payload",
                type="json",
                description="Task data (name, notes, assignee, projects, …).",
                display_options=DisplayOptions(
                    show={"operation": list(_DOCUMENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="text",
                display_name="Comment",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_ADD_COMMENT]}),
            ),
            PropertySchema(
                name="html_text",
                display_name="HTML Comment",
                type="string",
                description="Rich-text body (takes precedence over 'text').",
                display_options=DisplayOptions(show={"operation": [OP_ADD_COMMENT]}),
            ),
            PropertySchema(
                name="is_pinned",
                display_name="Pin Comment",
                type="boolean",
                display_options=DisplayOptions(show={"operation": [OP_ADD_COMMENT]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Asana REST call per input item."""
        access_token, enable_flags = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if enable_flags:
            headers[ENABLE_HEADER] = enable_flags
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
        msg = "Asana: an asana_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Asana: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    raw_flags = payload.get("enable_flags")
    if raw_flags in (None, ""):
        return token, ""
    if isinstance(raw_flags, str):
        parts = [part.strip() for part in raw_flags.split(",")]
    elif isinstance(raw_flags, (list, tuple)):
        parts = [str(part).strip() for part in raw_flags]
    else:
        msg = "Asana: credential 'enable_flags' must be a string or list"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, ",".join(part for part in parts if part)


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_TASKS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Asana: unsupported operation {operation!r}"
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
        logger.error("asana.request_failed", operation=operation, error=str(exc))
        msg = f"Asana: network error on {operation}: {exc}"
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
            "asana.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Asana {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("asana.ok", operation=operation, status=response.status_code)
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
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, str) and message:
                    phrase = first.get("help")
                    if isinstance(phrase, str) and phrase:
                        return f"{message} ({phrase})"
                    return message
    return f"HTTP {status_code}"
