"""Jira node — Cloud v3 REST API for issue tracking.

Dispatches to ``https://<site>.atlassian.net/rest/api/3/...`` with HTTP
Basic authentication (``email`` + ``api_token`` from
:class:`~weftlyflow.credentials.types.jira_cloud.JiraCloudCredential`).
The tenant's site slug lives on the credential, not on the node, so
multiple environments share the same workflow definition.

Parameters (all expression-capable):

* ``operation`` — ``get_issue``, ``create_issue``, ``update_issue``,
  ``delete_issue``, ``search_issues``, ``add_comment``.
* ``issue_key`` — for all operations except ``create_issue`` and
  ``search_issues``.
* ``project_key`` / ``summary`` / ``issue_type`` — for ``create_issue``.
* ``extra_fields`` — optional JSON merged into the ``fields`` payload on
  ``create_issue``.
* ``fields`` — JSON of updates for ``update_issue`` **or** list of
  field names to fetch on ``get_issue`` / ``search_issues``.
* ``expand`` — comma-separated list for ``get_issue``.
* ``delete_subtasks`` — boolean for ``delete_issue``.
* ``jql`` / ``max_results`` / ``start_at`` — for ``search_issues``.
* ``body`` — comment text for ``add_comment``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``; ``search_issues`` also surfaces a convenience
``issues`` list.
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
from weftlyflow.nodes.integrations.jira.constants import (
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_COMMENT,
    OP_CREATE_ISSUE,
    OP_DELETE_ISSUE,
    OP_GET_ISSUE,
    OP_SEARCH_ISSUES,
    OP_UPDATE_ISSUE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.jira.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "jira_cloud"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.jira_cloud",)
_ISSUE_KEY_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_ISSUE, OP_UPDATE_ISSUE, OP_DELETE_ISSUE, OP_ADD_COMMENT},
)

log = structlog.get_logger(__name__)


class JiraNode(BaseNode):
    """Dispatch a single Jira Cloud REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.jira",
        version=1,
        display_name="Jira",
        description="Manage Jira Cloud issues, searches, and comments.",
        icon="icons/jira.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "project-management"],
        documentation_url="https://developer.atlassian.com/cloud/jira/platform/rest/v3/",
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
                default=OP_GET_ISSUE,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_ISSUE, label="Get Issue"),
                    PropertyOption(value=OP_CREATE_ISSUE, label="Create Issue"),
                    PropertyOption(value=OP_UPDATE_ISSUE, label="Update Issue"),
                    PropertyOption(value=OP_DELETE_ISSUE, label="Delete Issue"),
                    PropertyOption(value=OP_SEARCH_ISSUES, label="Search Issues (JQL)"),
                    PropertyOption(value=OP_ADD_COMMENT, label="Add Comment"),
                ],
            ),
            PropertySchema(
                name="issue_key",
                display_name="Issue Key",
                type="string",
                placeholder="PROJ-123",
                display_options=DisplayOptions(
                    show={"operation": list(_ISSUE_KEY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="project_key",
                display_name="Project Key",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="summary",
                display_name="Summary",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="issue_type",
                display_name="Issue Type",
                type="string",
                default="Task",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="extra_fields",
                display_name="Extra Fields",
                type="json",
                description="Optional JSON merged into the 'fields' payload.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description=(
                    "For update: object of field→value. "
                    "For get/search: list of field names to fetch."
                ),
            ),
            PropertySchema(
                name="expand",
                display_name="Expand",
                type="string",
                description="Comma-separated list of fields to expand.",
                display_options=DisplayOptions(show={"operation": [OP_GET_ISSUE]}),
            ),
            PropertySchema(
                name="delete_subtasks",
                display_name="Delete Subtasks",
                type="boolean",
                default=False,
                display_options=DisplayOptions(show={"operation": [OP_DELETE_ISSUE]}),
            ),
            PropertySchema(
                name="jql",
                display_name="JQL",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_ISSUES]}),
            ),
            PropertySchema(
                name="max_results",
                display_name="Max Results",
                type="number",
                default=DEFAULT_SEARCH_LIMIT,
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_ISSUES]}),
            ),
            PropertySchema(
                name="start_at",
                display_name="Start At",
                type="number",
                default=0,
                display_options=DisplayOptions(show={"operation": [OP_SEARCH_ISSUES]}),
            ),
            PropertySchema(
                name="body",
                display_name="Comment Body",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_ADD_COMMENT]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Jira REST call per input item."""
        site, auth_header = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        base_url = f"https://{site}.atlassian.net"
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        auth_header=auth_header,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Jira: a jira_cloud credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    site = str(payload.get("site") or "").strip()
    email = str(payload.get("email") or "").strip()
    token = str(payload.get("api_token") or "").strip()
    if not site or not email or not token:
        msg = "Jira: credential must have 'site', 'email', and 'api_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    encoded = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
    return site, f"Basic {encoded}"


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    auth_header: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_GET_ISSUE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Jira: unsupported operation {operation!r}"
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
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("jira.request_failed", operation=operation, error=str(exc))
        msg = f"Jira: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_SEARCH_ISSUES and isinstance(payload, dict):
        issues = payload.get("issues", [])
        result["issues"] = issues if isinstance(issues, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "jira.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Jira {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("jira.ok", operation=operation, status=response.status_code)
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
        messages = payload.get("errorMessages")
        if isinstance(messages, list) and messages:
            return "; ".join(str(m) for m in messages)
        errors = payload.get("errors")
        if isinstance(errors, dict) and errors:
            return "; ".join(f"{k}: {v}" for k, v in errors.items())
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
