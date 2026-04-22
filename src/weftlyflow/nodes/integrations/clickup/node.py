"""ClickUp node — v2 REST API for task management.

Dispatches to ``https://api.clickup.com/api/v2/...`` with a **raw**
``Authorization: <token>`` header (no ``Bearer`` / ``Bot`` prefix —
ClickUp is explicit about this). The token is sourced from a
:class:`~weftlyflow.credentials.types.clickup_api.ClickUpApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``create_task``, ``get_task``, ``update_task``,
  ``delete_task``, ``list_tasks``.
* ``list_id`` — for ``create_task`` / ``list_tasks``.
* ``task_id`` — for get/update/delete.
* ``name`` — required for ``create_task``.
* ``description`` / ``status`` / ``priority`` — optional create fields.
* ``assignees`` — list of user ids on ``create_task``.
* ``extra_fields`` — optional JSON merged into the create body.
* ``fields`` — JSON of updates for ``update_task`` (allowed keys:
  ``name``, ``description``, ``status``, ``priority``, ``due_date``,
  ``due_date_time``, ``time_estimate``, ``start_date``,
  ``start_date_time``, ``assignees``, ``archived``, ``parent``).
* ``archived`` / ``page`` / ``order_by`` / ``subtasks`` / ``statuses`` —
  list knobs.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``. ``list_tasks`` also surfaces a convenience
``tasks`` list.
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
from weftlyflow.nodes.integrations.clickup.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_TASK,
    OP_DELETE_TASK,
    OP_GET_TASK,
    OP_LIST_TASKS,
    OP_UPDATE_TASK,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.clickup.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "clickup_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.clickup_api",)
_LIST_ID_OPERATIONS: frozenset[str] = frozenset({OP_CREATE_TASK, OP_LIST_TASKS})
_TASK_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_TASK, OP_UPDATE_TASK, OP_DELETE_TASK},
)

log = structlog.get_logger(__name__)


class ClickUpNode(BaseNode):
    """Dispatch a single ClickUp v2 task call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.clickup",
        version=1,
        display_name="ClickUp",
        description="Create, update, and list ClickUp tasks via the v2 REST API.",
        icon="icons/clickup.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "project-management"],
        documentation_url="https://clickup.com/api",
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
                    PropertyOption(value=OP_CREATE_TASK, label="Create Task"),
                    PropertyOption(value=OP_GET_TASK, label="Get Task"),
                    PropertyOption(value=OP_UPDATE_TASK, label="Update Task"),
                    PropertyOption(value=OP_DELETE_TASK, label="Delete Task"),
                    PropertyOption(value=OP_LIST_TASKS, label="List Tasks"),
                ],
            ),
            PropertySchema(
                name="list_id",
                display_name="List ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="task_id",
                display_name="Task ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_TASK_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TASK]}),
            ),
            PropertySchema(
                name="description",
                display_name="Description",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TASK]}),
            ),
            PropertySchema(
                name="status",
                display_name="Status",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TASK]}),
            ),
            PropertySchema(
                name="priority",
                display_name="Priority",
                type="number",
                description="1=Urgent, 2=High, 3=Normal, 4=Low.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TASK]}),
            ),
            PropertySchema(
                name="assignees",
                display_name="Assignees",
                type="json",
                description="List of user ids.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TASK]}),
            ),
            PropertySchema(
                name="extra_fields",
                display_name="Extra Fields",
                type="json",
                description="Optional JSON merged into the create body.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TASK]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_TASK]}),
            ),
            PropertySchema(
                name="archived",
                display_name="Archived",
                type="boolean",
                default=False,
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                default=0,
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="order_by",
                display_name="Order By",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="subtasks",
                display_name="Include Subtasks",
                type="boolean",
                default=False,
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
            PropertySchema(
                name="statuses",
                display_name="Statuses",
                type="string",
                description="Comma-separated list of statuses to include.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TASKS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one ClickUp v2 REST call per input item."""
        token = await _resolve_token(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
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
                        token=token,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_token(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "ClickUp: a clickup_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("api_token") or "").strip()
    if not token:
        msg = "ClickUp: credential has an empty 'api_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_TASKS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"ClickUp: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers={
                "Authorization": token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("clickup.request_failed", operation=operation, error=str(exc))
        msg = f"ClickUp: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_TASKS and isinstance(payload, dict):
        tasks = payload.get("tasks", [])
        result["tasks"] = tasks if isinstance(tasks, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "clickup.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"ClickUp {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("clickup.ok", operation=operation, status=response.status_code)
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
        err = payload.get("err")
        if isinstance(err, str) and err:
            return err
        message = payload.get("message") or payload.get("ECODE")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
