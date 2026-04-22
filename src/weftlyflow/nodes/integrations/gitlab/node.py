"""GitLab node — v4 REST API for issues and merge requests.

Dispatches to ``<base_url>/api/v4/projects/{id_or_path}/...`` with
``PRIVATE-TOKEN: <token>`` from a
:class:`~weftlyflow.credentials.types.gitlab_token.GitLabTokenCredential`.
The base URL lives on the credential, so the same workflow definition
works against gitlab.com and any self-hosted instance.

Parameters (all expression-capable):

* ``operation`` — ``get_issue``, ``create_issue``, ``update_issue``,
  ``list_issues``, ``add_comment``, ``list_merge_requests``.
* ``project_id`` — numeric ID or URL-encodable path
  (``group/subgroup/repo``).
* ``issue_iid`` — project-scoped issue IID for get/update/add_comment.
* ``title`` / ``description`` / ``labels`` / ``assignee_ids`` —
  ``create_issue``.
* ``fields`` — JSON of updates for ``update_issue`` (allowed keys:
  ``title``, ``description``, ``assignee_ids``, ``labels``,
  ``state_event``, ``milestone_id``, ``due_date``,
  ``discussion_locked``, ``confidential``).
* ``state`` / ``search`` / ``target_branch`` / ``per_page`` — list knobs.
* ``body`` — comment text for ``add_comment``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``. List operations surface ``issues`` or
``merge_requests`` convenience keys.
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
from weftlyflow.nodes.integrations.gitlab.constants import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_COMMENT,
    OP_CREATE_ISSUE,
    OP_GET_ISSUE,
    OP_LIST_ISSUES,
    OP_LIST_MERGE_REQUESTS,
    OP_UPDATE_ISSUE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.gitlab.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "gitlab_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.gitlab_token",)
_DEFAULT_BASE_URL: str = "https://gitlab.com"
_ISSUE_IID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_ISSUE, OP_UPDATE_ISSUE, OP_ADD_COMMENT},
)

log = structlog.get_logger(__name__)


class GitLabNode(BaseNode):
    """Dispatch a single GitLab v4 REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.gitlab",
        version=1,
        display_name="GitLab",
        description="Manage GitLab issues, comments, and merge requests.",
        icon="icons/gitlab.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "devops"],
        documentation_url="https://docs.gitlab.com/ee/api/rest/",
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
                    PropertyOption(value=OP_LIST_ISSUES, label="List Issues"),
                    PropertyOption(value=OP_ADD_COMMENT, label="Add Comment"),
                    PropertyOption(
                        value=OP_LIST_MERGE_REQUESTS, label="List Merge Requests",
                    ),
                ],
            ),
            PropertySchema(
                name="project_id",
                display_name="Project ID or Path",
                type="string",
                required=True,
                placeholder="group/subgroup/repo",
            ),
            PropertySchema(
                name="issue_iid",
                display_name="Issue IID",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_ISSUE_IID_OPERATIONS)},
                ),
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
                name="labels",
                display_name="Labels",
                type="string",
                description="Comma-separated labels.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ISSUE, OP_LIST_ISSUES]},
                ),
            ),
            PropertySchema(
                name="assignee_ids",
                display_name="Assignee IDs",
                type="json",
                description="List of numeric user ids.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_ISSUE]}),
            ),
            PropertySchema(
                name="body",
                display_name="Comment Body",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_ADD_COMMENT]}),
            ),
            PropertySchema(
                name="state",
                display_name="State",
                type="string",
                description="'opened', 'closed', 'merged' (MRs), or 'all'.",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ISSUES, OP_LIST_MERGE_REQUESTS]},
                ),
            ),
            PropertySchema(
                name="search",
                display_name="Search",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_ISSUES]}),
            ),
            PropertySchema(
                name="target_branch",
                display_name="Target Branch",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_MERGE_REQUESTS]},
                ),
            ),
            PropertySchema(
                name="per_page",
                display_name="Per Page",
                type="number",
                default=DEFAULT_LIST_LIMIT,
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_ISSUES, OP_LIST_MERGE_REQUESTS]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one GitLab v4 REST call per input item."""
        base_url, token = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
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
                        token=token,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "GitLab: a gitlab_token credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "GitLab: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    base_url = str(payload.get("base_url") or _DEFAULT_BASE_URL).strip().rstrip("/")
    if not base_url:
        base_url = _DEFAULT_BASE_URL
    return base_url, token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_GET_ISSUE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"GitLab: unsupported operation {operation!r}"
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
                "PRIVATE-TOKEN": token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("gitlab.request_failed", operation=operation, error=str(exc))
        msg = f"GitLab: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_ISSUES and isinstance(payload, list):
        result["issues"] = payload
    elif operation == OP_LIST_MERGE_REQUESTS and isinstance(payload, list):
        result["merge_requests"] = payload
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "gitlab.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"GitLab {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("gitlab.ok", operation=operation, status=response.status_code)
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
        message = payload.get("message") or payload.get("error")
        if isinstance(message, str) and message:
            return message
        if isinstance(message, dict) and message:
            return "; ".join(f"{k}: {v}" for k, v in message.items())
        if isinstance(message, list) and message:
            return "; ".join(str(m) for m in message)
    return f"HTTP {status_code}"
