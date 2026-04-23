"""Facebook Graph node — generic node/edge dispatcher for the Graph API.

Dispatches to the version-prefixed Graph host
(``https://graph.facebook.com/{api_version}``) using the credential
:class:`~weftlyflow.credentials.types.facebook_graph.FacebookGraphCredential`.
The credential signs every request with ``Authorization: Bearer
<token>`` and — when an ``app_secret`` is configured — appends the
HMAC-SHA256 ``appsecret_proof`` query parameter.

Parameters (all expression-capable):

* ``operation`` — ``get_me``, ``get_node``, ``list_edge``,
  ``create_edge``, ``delete_node``.
* ``node_id`` — Graph node identifier (page id, user id, post id, ...).
* ``edge`` — connection name for list/create edge ops (``posts``,
  ``feed``, ``comments``, ``accounts``, ...).
* ``fields`` — comma-separated field selector (``id,name,email``).
* ``body`` — JSON object for ``create_edge`` writes.
* ``limit`` / ``after`` / ``before`` — cursor pagination on edges.

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
from weftlyflow.nodes.integrations.facebook.constants import (
    DEFAULT_API_VERSION,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_EDGE,
    OP_DELETE_NODE,
    OP_GET_ME,
    OP_GET_NODE,
    OP_LIST_EDGE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.facebook.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_API_HOST: str = "https://graph.facebook.com"
_CREDENTIAL_SLOT: str = "facebook_graph"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.facebook_graph",)
_NODE_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_NODE, OP_LIST_EDGE, OP_CREATE_EDGE, OP_DELETE_NODE},
)
_EDGE_OPERATIONS: frozenset[str] = frozenset({OP_LIST_EDGE, OP_CREATE_EDGE})
_FIELDS_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_ME, OP_GET_NODE, OP_LIST_EDGE},
)

log = structlog.get_logger(__name__)


class FacebookGraphNode(BaseNode):
    """Dispatch a single Facebook Graph call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.facebook_graph",
        version=1,
        display_name="Facebook Graph",
        description="Read/write the Facebook Graph (pages, posts, users, edges).",
        icon="icons/facebook.svg",
        category=NodeCategory.INTEGRATION,
        group=["social", "marketing"],
        documentation_url="https://developers.facebook.com/docs/graph-api",
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
                default=OP_GET_ME,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_ME, label="Get Me"),
                    PropertyOption(value=OP_GET_NODE, label="Get Node"),
                    PropertyOption(value=OP_LIST_EDGE, label="List Edge"),
                    PropertyOption(value=OP_CREATE_EDGE, label="Create Edge"),
                    PropertyOption(value=OP_DELETE_NODE, label="Delete Node"),
                ],
            ),
            PropertySchema(
                name="node_id",
                display_name="Node ID",
                type="string",
                description="Graph node id (page, user, post, ...).",
                display_options=DisplayOptions(
                    show={"operation": list(_NODE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="edge",
                display_name="Edge",
                type="string",
                description="Connection name (e.g. posts, feed, comments).",
                display_options=DisplayOptions(
                    show={"operation": list(_EDGE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="string",
                description="Comma-separated field selector (id,name,email).",
                display_options=DisplayOptions(
                    show={"operation": list(_FIELDS_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="body",
                display_name="Body",
                type="json",
                description='Write payload, e.g. {"message": "Hello"}.',
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_EDGE]},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_EDGE]},
                ),
            ),
            PropertySchema(
                name="after",
                display_name="After Cursor",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_EDGE]},
                ),
            ),
            PropertySchema(
                name="before",
                display_name="Before Cursor",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_EDGE]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Facebook Graph call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        version = str(payload.get("api_version") or DEFAULT_API_VERSION).strip()
        base_url = f"{_API_HOST}/{version}"
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
        msg = "Facebook: a facebook_graph credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Facebook: credential has an empty 'access_token'"
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
    operation = str(params.get("operation") or OP_GET_ME).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Facebook: unsupported operation {operation!r}"
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
        logger.error("facebook.request_failed", operation=operation, error=str(exc))
        msg = f"Facebook: network error on {operation}: {exc}"
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
            "facebook.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Facebook {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("facebook.ok", operation=operation, status=response.status_code)
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
            code = error.get("code")
            if code is not None:
                return f"code={code}"
    return f"HTTP {status_code}"
