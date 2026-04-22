"""Linear node — GraphQL API for issues, teams, projects.

Single-endpoint POST to ``https://api.linear.app/graphql`` with an
``Authorization: <api_key>`` header (no prefix) sourced from
:class:`~weftlyflow.credentials.types.linear_api.LinearApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``list_issues``, ``get_issue``, ``create_issue``,
  ``update_issue``, ``list_teams``, ``list_projects``.
* ``issue_id`` — target issue (get/update).
* ``team_id`` / ``title`` / ``description`` — ``create_issue``.
* ``extra`` — optional ``IssueCreateInput`` overrides (priority,
  stateId, assigneeId, labelIds, ...).
* ``fields`` — required ``IssueUpdateInput`` for ``update_issue``.
* ``filter`` — JSON ``IssueFilter`` object for ``list_issues``.
* ``first`` / ``after`` — cursor pagination for list queries.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response.data`` (or surfaces ``errors`` as a NodeExecutionError).
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
from weftlyflow.nodes.integrations.linear.constants import (
    API_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_ISSUE,
    OP_GET_ISSUE,
    OP_LIST_ISSUES,
    OP_LIST_PROJECTS,
    OP_LIST_TEAMS,
    OP_UPDATE_ISSUE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.linear.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "linear_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.linear_api",)
_ISSUE_ID_OPERATIONS: frozenset[str] = frozenset({OP_GET_ISSUE, OP_UPDATE_ISSUE})
_LIST_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_ISSUES, OP_LIST_TEAMS, OP_LIST_PROJECTS},
)

log = structlog.get_logger(__name__)


class LinearNode(BaseNode):
    """Dispatch a single Linear GraphQL call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.linear",
        version=1,
        display_name="Linear",
        description="Manage Linear issues, teams, and projects via GraphQL.",
        icon="icons/linear.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "project-management"],
        documentation_url="https://developers.linear.app/docs/graphql/",
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
                default=OP_LIST_ISSUES,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_ISSUES, label="List Issues"),
                    PropertyOption(value=OP_GET_ISSUE, label="Get Issue"),
                    PropertyOption(value=OP_CREATE_ISSUE, label="Create Issue"),
                    PropertyOption(value=OP_UPDATE_ISSUE, label="Update Issue"),
                    PropertyOption(value=OP_LIST_TEAMS, label="List Teams"),
                    PropertyOption(value=OP_LIST_PROJECTS, label="List Projects"),
                ],
            ),
            PropertySchema(
                name="issue_id",
                display_name="Issue ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_ISSUE_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="team_id",
                display_name="Team ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="description",
                display_name="Description",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="extra",
                display_name="Extra Fields",
                type="json",
                description="Optional IssueCreateInput overrides.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="IssueUpdateInput body for update_issue.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_ISSUE]}),
            ),
            PropertySchema(
                name="filter",
                display_name="Filter",
                type="json",
                description="GraphQL IssueFilter object.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_ISSUES]}),
            ),
            PropertySchema(
                name="first",
                display_name="Page Size",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="after",
                display_name="Cursor",
                type="string",
                description="Opaque cursor from previous pageInfo.endCursor.",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Linear GraphQL call per input item."""
        api_key = await _resolve_credential(ctx)
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
                        api_key=api_key,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credential(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Linear: a linear_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "Linear: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return api_key


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_ISSUES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Linear: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        operation_name, query, variables = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    body: dict[str, Any] = {
        "query": query,
        "variables": variables,
        "operationName": operation_name,
    }
    try:
        response = await client.post(
            API_URL,
            json=body,
            headers={
                "Authorization": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("linear.request_failed", operation=operation, error=str(exc))
        msg = f"Linear: network error on {operation}: {exc}"
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
            "linear.http_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Linear {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    graphql_error = _graphql_error(payload)
    if graphql_error is not None:
        logger.warning(
            "linear.graphql_error", operation=operation, error=graphql_error,
        )
        msg = f"Linear {operation} failed: {graphql_error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("linear.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _graphql_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0]
    if isinstance(first, dict):
        message = first.get("message")
        if isinstance(message, str) and message:
            return message
    return str(first)


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, str) and message:
                    return message
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
