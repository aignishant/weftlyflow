"""Ghost Admin node — posts, pages, and members via the Admin API.

Dispatches to a credential-owned ``base_url`` with the distinctive
per-request HS256 JWT auth shape (``Authorization: Ghost <jwt>``) where
the credential mints a fresh token for every outbound request.
Token minting is handled by
:class:`~weftlyflow.credentials.types.ghost_admin.GhostAdminCredential`.

Distinctive Ghost semantics:

* Resource envelopes — writes/reads wrap objects inside a
  plural-named key, e.g. ``{"posts": [{...}]}``.
* Optimistic concurrency on updates — the caller must echo back the
  current ``updated_at`` in the payload or Ghost returns 409.

Parameters (all expression-capable):

* ``operation`` — ``list_posts``, ``get_post``, ``create_post``,
  ``update_post``, ``delete_post``, ``list_members``,
  ``create_member``.
* ``post_id`` — target for single-post operations.
* ``title`` / ``html`` / ``lexical`` — post content fields.
* ``updated_at`` — required on ``update_post``.
* ``email`` / ``name`` / ``labels`` — member creation.

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
from weftlyflow.nodes.integrations.ghost.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_MEMBER,
    OP_CREATE_POST,
    OP_DELETE_POST,
    OP_GET_POST,
    OP_LIST_MEMBERS,
    OP_LIST_POSTS,
    OP_UPDATE_POST,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.ghost.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "ghost_admin"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.ghost_admin",)
_POST_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_POST, OP_UPDATE_POST, OP_DELETE_POST},
)
_CONTENT_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_POST, OP_UPDATE_POST},
)
_LIST_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_POSTS, OP_LIST_MEMBERS},
)

log = structlog.get_logger(__name__)


class GhostNode(BaseNode):
    """Dispatch a single Ghost Admin API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.ghost",
        version=1,
        display_name="Ghost",
        description="Manage posts and members on a Ghost blog via the Admin API.",
        icon="icons/ghost.svg",
        category=NodeCategory.INTEGRATION,
        group=["cms", "publishing"],
        documentation_url="https://ghost.org/docs/admin-api/",
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
                default=OP_LIST_POSTS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_POSTS, label="List Posts"),
                    PropertyOption(value=OP_GET_POST, label="Get Post"),
                    PropertyOption(value=OP_CREATE_POST, label="Create Post"),
                    PropertyOption(value=OP_UPDATE_POST, label="Update Post"),
                    PropertyOption(value=OP_DELETE_POST, label="Delete Post"),
                    PropertyOption(value=OP_LIST_MEMBERS, label="List Members"),
                    PropertyOption(value=OP_CREATE_MEMBER, label="Create Member"),
                ],
            ),
            PropertySchema(
                name="post_id",
                display_name="Post ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_POST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_POST]},
                ),
            ),
            PropertySchema(
                name="html",
                display_name="HTML Content",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CONTENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="lexical",
                display_name="Lexical JSON",
                type="json",
                display_options=DisplayOptions(
                    show={"operation": list(_CONTENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="status",
                display_name="Status",
                type="options",
                options=[
                    PropertyOption(value="draft", label="Draft"),
                    PropertyOption(value="published", label="Published"),
                    PropertyOption(value="scheduled", label="Scheduled"),
                ],
                display_options=DisplayOptions(
                    show={"operation": list(_CONTENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="tags",
                display_name="Tags",
                type="json",
                description="Array of tag names or full tag objects.",
                display_options=DisplayOptions(
                    show={"operation": list(_CONTENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="updated_at",
                display_name="Updated At (required)",
                type="string",
                description="Current 'updated_at' of the post (optimistic concurrency).",
                display_options=DisplayOptions(
                    show={"operation": [OP_UPDATE_POST]},
                ),
            ),
            PropertySchema(
                name="email",
                display_name="Email",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_MEMBER]},
                ),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_MEMBER]},
                ),
            ),
            PropertySchema(
                name="labels",
                display_name="Labels",
                type="json",
                description="Array of label strings.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_MEMBER]},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="filter",
                display_name="Filter (NQL)",
                type="string",
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
        """Issue one Ghost Admin API call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            msg = "Ghost: credential has an empty 'base_url'"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
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
        msg = "Ghost: a ghost_admin credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("admin_api_key") or "").strip():
        msg = "Ghost: credential has an empty 'admin_api_key'"
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
    operation = str(params.get("operation") or OP_LIST_POSTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Ghost: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
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
        logger.error("ghost.request_failed", operation=operation, error=str(exc))
        msg = f"Ghost: network error on {operation}: {exc}"
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
            "ghost.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Ghost {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("ghost.ok", operation=operation, status=response.status_code)
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
                    return message
                context = first.get("context")
                if isinstance(context, str) and context:
                    return context
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
