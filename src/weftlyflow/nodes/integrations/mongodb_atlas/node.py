"""MongoDB Atlas node — projects, clusters, database users.

Dispatches against ``https://cloud.mongodb.com/api/atlas/v2`` using HTTP
Digest authentication. Because Digest requires a challenge/response, the
auth handler is attached to the :class:`httpx.AsyncClient` (via
:class:`httpx.DigestAuth`) rather than injected per-request — the
credential's :meth:`inject` is a deliberate no-op.

Every call carries ``Accept: application/vnd.atlas.2024-05-30+json`` so
Atlas resolves the correct API version.

Parameters (all expression-capable):

* ``operation`` — ``list_projects`` / ``list_clusters`` /
  ``get_cluster`` / ``list_db_users``.
* ``group_id`` — Atlas project ID; required for all cluster/user ops.
* ``cluster_name`` — required for ``get_cluster``.
* ``page_num`` / ``items_per_page`` — pagination on list endpoints.

Output: one item per input item with ``operation``, ``status``, and
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
from weftlyflow.nodes.integrations.mongodb_atlas.constants import (
    ACCEPT_MEDIA_TYPE,
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_GET_CLUSTER,
    OP_LIST_CLUSTERS,
    OP_LIST_DB_USERS,
    OP_LIST_PROJECTS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.mongodb_atlas.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "mongodb_atlas_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.mongodb_atlas_api",)

log = structlog.get_logger(__name__)


class MongoDbAtlasNode(BaseNode):
    """Dispatch a single MongoDB Atlas Admin API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.mongodb_atlas",
        version=1,
        display_name="MongoDB Atlas",
        description="List projects, clusters, and database users on MongoDB Atlas.",
        icon="icons/mongodb_atlas.svg",
        category=NodeCategory.INTEGRATION,
        group=["database"],
        documentation_url="https://www.mongodb.com/docs/atlas/reference/api-resources-spec/",
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
                default=OP_LIST_PROJECTS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_PROJECTS, label="List Projects"),
                    PropertyOption(value=OP_LIST_CLUSTERS, label="List Clusters"),
                    PropertyOption(value=OP_GET_CLUSTER, label="Get Cluster"),
                    PropertyOption(value=OP_LIST_DB_USERS, label="List Database Users"),
                ],
            ),
            PropertySchema(
                name="group_id",
                display_name="Project (Group) ID",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_CLUSTERS,
                            OP_GET_CLUSTER,
                            OP_LIST_DB_USERS,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="cluster_name",
                display_name="Cluster Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_GET_CLUSTER]}),
            ),
            PropertySchema(
                name="page_num",
                display_name="Page Number",
                type="number",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_PROJECTS,
                            OP_LIST_CLUSTERS,
                            OP_LIST_DB_USERS,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="items_per_page",
                display_name="Items Per Page",
                type="number",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_LIST_PROJECTS,
                            OP_LIST_CLUSTERS,
                            OP_LIST_DB_USERS,
                        ],
                    },
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Atlas call per input item."""
        public_key, private_key = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL,
            auth=httpx.DigestAuth(public_key, private_key),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(ctx, item, client=client, logger=bound),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "MongoDB Atlas: a mongodb_atlas_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _injector, payload = credential
    public_key = str(payload.get("public_key") or "").strip()
    private_key = str(payload.get("private_key") or "").strip()
    if not public_key or not private_key:
        msg = "MongoDB Atlas: credential has an empty 'public_key' or 'private_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return public_key, private_key


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_PROJECTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"MongoDB Atlas: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers = {"Accept": ACCEPT_MEDIA_TYPE}
    if body is not None:
        headers["Content-Type"] = ACCEPT_MEDIA_TYPE
    try:
        response = await client.request(
            method, path, params=query or None, json=body, headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.error("mongodb_atlas.request_failed", operation=operation, error=str(exc))
        msg = f"MongoDB Atlas: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    parsed = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": parsed,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(parsed, response.status_code)
        logger.warning(
            "mongodb_atlas.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"MongoDB Atlas {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("mongodb_atlas.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, dict):
        for key in ("detail", "reason", "errorCode"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
