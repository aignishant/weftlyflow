"""Notion node — query databases, create pages, retrieve pages.

Dispatches to Notion's REST API at ``https://api.notion.com``. Every
request carries ``Authorization: Bearer secret_...`` and the required
``Notion-Version`` header — both supplied by a
:class:`~weftlyflow.credentials.types.notion_api.NotionApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``query_database``, ``create_page``, ``retrieve_page``.
* ``database_id`` — UUID, required for ``query_database``.
* ``parent_database_id`` / ``parent_page_id`` — for ``create_page``; one is
  required.
* ``properties`` — object literal shaped per Notion's property schema.
* ``children`` — optional block children list for ``create_page``.
* ``filter`` / ``sorts`` — optional payloads for ``query_database``.
* ``page_size`` / ``start_cursor`` — pagination for ``query_database``.
* ``page_id`` — UUID, required for ``retrieve_page``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` dict. For ``query_database`` the convenience key
``results`` lifts ``response["results"]``.
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
from weftlyflow.nodes.integrations.notion.constants import (
    API_BASE_URL,
    DEFAULT_NOTION_VERSION,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_PAGE,
    OP_QUERY_DATABASE,
    OP_RETRIEVE_PAGE,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.notion.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "notion_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.notion_api",)

log = structlog.get_logger(__name__)


class NotionNode(BaseNode):
    """Dispatch a single Notion REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.notion",
        version=1,
        display_name="Notion",
        description="Query Notion databases, create pages, and retrieve pages.",
        icon="icons/notion.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "knowledge"],
        documentation_url="https://developers.notion.com/reference/intro",
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
                default=OP_QUERY_DATABASE,
                required=True,
                options=[
                    PropertyOption(value=OP_QUERY_DATABASE, label="Query Database"),
                    PropertyOption(value=OP_CREATE_PAGE, label="Create Page"),
                    PropertyOption(value=OP_RETRIEVE_PAGE, label="Retrieve Page"),
                ],
            ),
            PropertySchema(
                name="database_id",
                display_name="Database ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_QUERY_DATABASE]}),
            ),
            PropertySchema(
                name="parent_database_id",
                display_name="Parent Database ID",
                type="string",
                description="Set this OR parent_page_id for create_page.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_PAGE]}),
            ),
            PropertySchema(
                name="parent_page_id",
                display_name="Parent Page ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_PAGE]}),
            ),
            PropertySchema(
                name="properties",
                display_name="Properties",
                type="json",
                description="Notion property schema (object).",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_PAGE]}),
            ),
            PropertySchema(
                name="children",
                display_name="Children Blocks",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_PAGE]}),
            ),
            PropertySchema(
                name="filter",
                display_name="Filter",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_QUERY_DATABASE]}),
            ),
            PropertySchema(
                name="sorts",
                display_name="Sorts",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_QUERY_DATABASE]}),
            ),
            PropertySchema(
                name="page_size",
                display_name="Page Size",
                type="number",
                default=DEFAULT_PAGE_SIZE,
                display_options=DisplayOptions(show={"operation": [OP_QUERY_DATABASE]}),
            ),
            PropertySchema(
                name="start_cursor",
                display_name="Start Cursor",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_QUERY_DATABASE]}),
            ),
            PropertySchema(
                name="page_id",
                display_name="Page ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_RETRIEVE_PAGE]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Notion REST call per input item."""
        token, version = await _resolve_credential(ctx)
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
                        notion_version=version,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credential(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Notion: a Notion API credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Notion: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    version = str(payload.get("notion_version") or DEFAULT_NOTION_VERSION).strip()
    return token, version or DEFAULT_NOTION_VERSION


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    notion_version: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_QUERY_DATABASE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Notion: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.request(
            method,
            path,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": notion_version,
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("notion.request_failed", operation=operation, error=str(exc))
        msg = f"Notion: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_QUERY_DATABASE and isinstance(payload, dict):
        value = payload.get("results", [])
        result["results"] = value if isinstance(value, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "notion.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Notion {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("notion.ok", operation=operation, status=response.status_code)
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
