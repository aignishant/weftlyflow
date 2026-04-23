"""Harvest node — time entries, projects, authenticated user.

Dispatches against ``https://api.harvestapp.com`` with two headers
that are set by the
:class:`~weftlyflow.credentials.types.harvest_api.HarvestApiCredential`:

* ``Authorization: Bearer <access_token>``.
* ``Harvest-Account-ID: <account_id>`` — scopes the call to a specific
  Harvest account (a single PAT can have access to several).

Parameters (all expression-capable):

* ``operation`` — ``list_time_entries`` / ``create_time_entry`` /
  ``list_projects`` / ``get_user_me``.
* ``project_id`` / ``task_id`` / ``spent_date`` / ``hours`` /
  ``started_time`` / ``ended_time`` / ``notes`` / ``user_id`` — create.
* ``page`` / ``per_page`` — pagination on list endpoints.
* ``is_active`` / ``client_id`` / ``updated_since`` — project filters.
* ``user_id`` / ``from`` / ``to`` — time-entry filters.

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
from weftlyflow.nodes.integrations.harvest.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_TIME_ENTRY,
    OP_GET_USER_ME,
    OP_LIST_PROJECTS,
    OP_LIST_TIME_ENTRIES,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.harvest.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "harvest_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.harvest_api",)

log = structlog.get_logger(__name__)


class HarvestNode(BaseNode):
    """Dispatch a single Harvest API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.harvest",
        version=1,
        display_name="Harvest",
        description="Read/write time entries, list projects, and fetch user info from Harvest.",
        icon="icons/harvest.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity"],
        documentation_url="https://help.getharvest.com/api-v2/",
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
                default=OP_LIST_TIME_ENTRIES,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_TIME_ENTRIES, label="List Time Entries"),
                    PropertyOption(value=OP_CREATE_TIME_ENTRY, label="Create Time Entry"),
                    PropertyOption(value=OP_LIST_PROJECTS, label="List Projects"),
                    PropertyOption(value=OP_GET_USER_ME, label="Get Authenticated User"),
                ],
            ),
            PropertySchema(
                name="project_id",
                display_name="Project ID",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_CREATE_TIME_ENTRY, OP_LIST_TIME_ENTRIES],
                    },
                ),
            ),
            PropertySchema(
                name="task_id",
                display_name="Task ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TIME_ENTRY]}),
            ),
            PropertySchema(
                name="spent_date",
                display_name="Spent Date (YYYY-MM-DD)",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TIME_ENTRY]}),
            ),
            PropertySchema(
                name="hours",
                display_name="Hours",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TIME_ENTRY]}),
            ),
            PropertySchema(
                name="started_time",
                display_name="Started Time",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TIME_ENTRY]}),
            ),
            PropertySchema(
                name="ended_time",
                display_name="Ended Time",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TIME_ENTRY]}),
            ),
            PropertySchema(
                name="notes",
                display_name="Notes",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_TIME_ENTRY]}),
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_CREATE_TIME_ENTRY, OP_LIST_TIME_ENTRIES],
                    },
                ),
            ),
            PropertySchema(
                name="from",
                display_name="From Date (YYYY-MM-DD)",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TIME_ENTRIES]}),
            ),
            PropertySchema(
                name="to",
                display_name="To Date (YYYY-MM-DD)",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_TIME_ENTRIES]}),
            ),
            PropertySchema(
                name="is_active",
                display_name="Active Only",
                type="boolean",
                display_options=DisplayOptions(show={"operation": [OP_LIST_PROJECTS]}),
            ),
            PropertySchema(
                name="client_id",
                display_name="Client ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_PROJECTS]}),
            ),
            PropertySchema(
                name="updated_since",
                display_name="Updated Since (ISO-8601)",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_PROJECTS]}),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_TIME_ENTRIES, OP_LIST_PROJECTS]},
                ),
            ),
            PropertySchema(
                name="per_page",
                display_name="Page Size",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_TIME_ENTRIES, OP_LIST_PROJECTS]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Harvest call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, injector=injector,
                        creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Harvest: a harvest_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("access_token") or "").strip():
        msg = "Harvest: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not str(payload.get("account_id") or "").strip():
        msg = "Harvest: credential has an empty 'account_id'"
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
    operation = str(params.get("operation") or OP_LIST_TIME_ENTRIES).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Harvest: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = client.build_request(
        method, path, params=query or None, json=body, headers=headers,
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("harvest.request_failed", operation=operation, error=str(exc))
        msg = f"Harvest: network error on {operation}: {exc}"
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
            "harvest.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Harvest {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("harvest.ok", operation=operation, status=response.status_code)
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
        for key in ("error_description", "message", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
