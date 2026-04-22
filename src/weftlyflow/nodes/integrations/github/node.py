"""GitHub node — issues, comments, and repo metadata.

The node dispatches to one of four operations against GitHub's REST API at
``https://api.github.com``. Every request carries
``Authorization: Bearer <token>`` from a
:class:`~weftlyflow.credentials.types.bearer_token.BearerTokenCredential`
(classic PAT or fine-grained token) plus the
``Accept: application/vnd.github+json`` and ``X-GitHub-Api-Version`` headers
GitHub recommends for REST v3.

Parameters (all expression-capable):

* ``operation`` — ``create_issue``, ``list_issues``, ``get_repo``,
  ``create_comment``.
* ``owner`` / ``repo`` — required for every operation.
* ``title`` / ``body`` — issue text (``body`` also carries comment text).
* ``labels`` / ``assignees`` — optional comma-separated strings or lists.
* ``state`` — ``open`` / ``closed`` / ``all`` for list_issues.
* ``per_page`` / ``page`` — pagination knobs for list_issues.
* ``issue_number`` — required for create_comment.

Credentials:

* slot ``"github_api"`` — a generic
  :class:`~weftlyflow.credentials.types.bearer_token.BearerTokenCredential`
  row. The node reads the ``token`` field directly.

Output: one item per input item, carrying ``operation``, ``status``,
``response`` (parsed JSON or raw text), and — for ``list_issues`` — a
convenience ``issues`` list.
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
from weftlyflow.nodes.integrations.github.constants import (
    ACCEPT_HEADER,
    API_BASE_URL,
    API_VERSION_HEADER,
    DEFAULT_LIST_PER_PAGE,
    DEFAULT_TIMEOUT_SECONDS,
    ISSUE_STATE_ALL,
    ISSUE_STATE_CLOSED,
    ISSUE_STATE_OPEN,
    OP_CREATE_COMMENT,
    OP_CREATE_ISSUE,
    OP_GET_REPO,
    OP_LIST_ISSUES,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.github.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "github_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.bearer_token",)
_MESSAGE_OPERATIONS: frozenset[str] = frozenset({OP_CREATE_ISSUE, OP_CREATE_COMMENT})

log = structlog.get_logger(__name__)


class GitHubNode(BaseNode):
    """Dispatch a single GitHub REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.github",
        version=1,
        display_name="GitHub",
        description="Create and list issues, fetch repo metadata, post comments.",
        icon="icons/github.svg",
        category=NodeCategory.INTEGRATION,
        group=["developer", "productivity"],
        documentation_url="https://docs.github.com/en/rest",
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
                default=OP_CREATE_ISSUE,
                required=True,
                options=[
                    PropertyOption(value=OP_CREATE_ISSUE, label="Create Issue"),
                    PropertyOption(value=OP_LIST_ISSUES, label="List Issues"),
                    PropertyOption(value=OP_GET_REPO, label="Get Repository"),
                    PropertyOption(value=OP_CREATE_COMMENT, label="Create Comment"),
                ],
            ),
            PropertySchema(
                name="owner",
                display_name="Owner",
                type="string",
                required=True,
                description="User or organisation that owns the repo.",
            ),
            PropertySchema(
                name="repo",
                display_name="Repository",
                type="string",
                required=True,
                description="Repository name (no owner prefix).",
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="body",
                display_name="Body",
                type="string",
                description="Issue body (create_issue) or comment text (create_comment).",
                display_options=DisplayOptions(
                    show={"operation": list(_MESSAGE_OPERATIONS)},
                ),
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
                name="assignees",
                display_name="Assignees",
                type="string",
                description="Comma-separated usernames.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ISSUE]}),
            ),
            PropertySchema(
                name="issue_number",
                display_name="Issue Number",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_COMMENT]}),
            ),
            PropertySchema(
                name="state",
                display_name="State",
                type="options",
                default=ISSUE_STATE_OPEN,
                options=[
                    PropertyOption(value=ISSUE_STATE_OPEN, label="Open"),
                    PropertyOption(value=ISSUE_STATE_CLOSED, label="Closed"),
                    PropertyOption(value=ISSUE_STATE_ALL, label="All"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_LIST_ISSUES]}),
            ),
            PropertySchema(
                name="per_page",
                display_name="Per Page",
                type="number",
                default=DEFAULT_LIST_PER_PAGE,
                display_options=DisplayOptions(show={"operation": [OP_LIST_ISSUES]}),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_ISSUES]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one GitHub REST call per input item."""
        token = await _resolve_token(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(ctx, item, client=client, token=token, logger=bound),
                )
        return [results]


async def _resolve_token(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "GitHub: a bearer-token credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("token") or "").strip()
    if not token:
        msg = "GitHub: credential has an empty 'token'"
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
    operation = str(params.get("operation") or OP_CREATE_ISSUE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"GitHub: unsupported operation {operation!r}"
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
                "Authorization": f"Bearer {token}",
                "Accept": ACCEPT_HEADER,
                "X-GitHub-Api-Version": API_VERSION_HEADER,
            },
        )
    except httpx.HTTPError as exc:
        logger.error("github.request_failed", operation=operation, error=str(exc))
        msg = f"GitHub: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_ISSUES:
        result["issues"] = payload if isinstance(payload, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "github.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"GitHub {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("github.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
