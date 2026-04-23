"""Bitbucket Cloud node — repositories, pull requests, and issues via the v2 API.

Dispatches to ``https://api.bitbucket.org`` with HTTP Basic auth
(username + scoped app password) and the **workspace slug** drawn
from the credential
:class:`~weftlyflow.credentials.types.bitbucket_api.BitbucketApiCredential`.
The workspace is path-scoped: every URL is prefixed with
``/2.0/repositories/{workspace}/...``. A per-call ``workspace`` param
overrides the credential default for cross-workspace operations.

Parameters (all expression-capable):

* ``operation`` — ``list_repositories``, ``get_repository``,
  ``list_pull_requests``, ``get_pull_request``, ``create_pull_request``,
  ``list_issues``, ``create_issue``.
* ``workspace`` — optional override (defaults to credential's).
* ``repo_slug`` — repository slug (e.g. ``my-repo``).
* ``pull_request_id`` — target PR.
* ``title`` / ``source_branch`` / ``destination_branch`` /
  ``description`` / ``close_source_branch`` — PR creation.
* ``content`` / ``kind`` / ``priority`` — issue creation.
* ``state`` / ``role`` / ``q`` / ``page`` / ``pagelen`` — list filters.

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
from weftlyflow.nodes.integrations.bitbucket.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_ISSUE,
    OP_CREATE_PULL_REQUEST,
    OP_GET_PULL_REQUEST,
    OP_GET_REPOSITORY,
    OP_LIST_ISSUES,
    OP_LIST_PULL_REQUESTS,
    OP_LIST_REPOSITORIES,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.bitbucket.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_API_HOST: str = "https://api.bitbucket.org"
_CREDENTIAL_SLOT: str = "bitbucket_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.bitbucket_api",)
_REPO_OPERATIONS: frozenset[str] = frozenset(
    {
        OP_GET_REPOSITORY,
        OP_LIST_PULL_REQUESTS,
        OP_GET_PULL_REQUEST,
        OP_CREATE_PULL_REQUEST,
        OP_LIST_ISSUES,
        OP_CREATE_ISSUE,
    },
)
_LIST_PR_ISSUE_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_PULL_REQUESTS, OP_LIST_ISSUES, OP_LIST_REPOSITORIES},
)
_PR_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_PULL_REQUEST, OP_CREATE_PULL_REQUEST},
)

log = structlog.get_logger(__name__)


class BitbucketNode(BaseNode):
    """Dispatch a single Bitbucket Cloud v2 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.bitbucket",
        version=1,
        display_name="Bitbucket Cloud",
        description="Manage Bitbucket Cloud repositories, pull requests, and issues.",
        icon="icons/bitbucket.svg",
        category=NodeCategory.INTEGRATION,
        group=["devops", "vcs"],
        documentation_url="https://developer.atlassian.com/cloud/bitbucket/rest/intro/",
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
                default=OP_LIST_REPOSITORIES,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_REPOSITORIES, label="List Repositories"),
                    PropertyOption(value=OP_GET_REPOSITORY, label="Get Repository"),
                    PropertyOption(value=OP_LIST_PULL_REQUESTS, label="List Pull Requests"),
                    PropertyOption(value=OP_GET_PULL_REQUEST, label="Get Pull Request"),
                    PropertyOption(value=OP_CREATE_PULL_REQUEST, label="Create Pull Request"),
                    PropertyOption(value=OP_LIST_ISSUES, label="List Issues"),
                    PropertyOption(value=OP_CREATE_ISSUE, label="Create Issue"),
                ],
            ),
            PropertySchema(
                name="workspace",
                display_name="Workspace Override",
                type="string",
                description="Falls back to the credential's workspace if blank.",
            ),
            PropertySchema(
                name="repo_slug",
                display_name="Repository Slug",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_REPO_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="pull_request_id",
                display_name="Pull Request ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_GET_PULL_REQUEST]},
                ),
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PULL_REQUEST, OP_CREATE_ISSUE]},
                ),
            ),
            PropertySchema(
                name="source_branch",
                display_name="Source Branch",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PULL_REQUEST]},
                ),
            ),
            PropertySchema(
                name="destination_branch",
                display_name="Destination Branch",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PULL_REQUEST]},
                ),
            ),
            PropertySchema(
                name="description",
                display_name="Description",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PULL_REQUEST]},
                ),
            ),
            PropertySchema(
                name="close_source_branch",
                display_name="Close Source Branch on Merge",
                type="boolean",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PULL_REQUEST]},
                ),
            ),
            PropertySchema(
                name="content",
                display_name="Content (raw markdown)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ISSUE]},
                ),
            ),
            PropertySchema(
                name="kind",
                display_name="Kind",
                type="string",
                description="bug | enhancement | proposal | task",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ISSUE]},
                ),
            ),
            PropertySchema(
                name="priority",
                display_name="Priority",
                type="string",
                description="trivial | minor | major | critical | blocker",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_ISSUE]},
                ),
            ),
            PropertySchema(
                name="state",
                display_name="State",
                type="string",
                description="OPEN | MERGED | DECLINED | SUPERSEDED",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_PULL_REQUESTS]},
                ),
            ),
            PropertySchema(
                name="role",
                display_name="Role",
                type="string",
                description="owner | admin | contributor | member",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_REPOSITORIES]},
                ),
            ),
            PropertySchema(
                name="q",
                display_name="BBQL Filter",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_REPOSITORIES, OP_LIST_ISSUES]},
                ),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_REPOSITORIES]},
                ),
            ),
            PropertySchema(
                name="pagelen",
                display_name="Page Length",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_PR_ISSUE_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Bitbucket v2 call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        default_workspace = str(payload.get("workspace") or "").strip()
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=_API_HOST, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx,
                        item,
                        client=client,
                        injector=injector,
                        creds=payload,
                        workspace=default_workspace,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Bitbucket: a bitbucket_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("username") or "").strip():
        msg = "Bitbucket: credential has an empty 'username'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not str(payload.get("app_password") or "").strip():
        msg = "Bitbucket: credential has an empty 'app_password'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    workspace: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_REPOSITORIES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Bitbucket: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params, workspace=workspace)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = client.build_request(
        method,
        path,
        params=query or None,
        json=body,
        headers=request_headers,
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("bitbucket.request_failed", operation=operation, error=str(exc))
        msg = f"Bitbucket: network error on {operation}: {exc}"
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
            "bitbucket.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Bitbucket {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("bitbucket.ok", operation=operation, status=response.status_code)
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
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
