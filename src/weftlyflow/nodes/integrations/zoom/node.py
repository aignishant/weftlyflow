"""Zoom node — Meetings API lifecycle operations.

Dispatches to ``api.zoom.us/v2`` with ``Authorization: Bearer
<access_token>`` sourced from
:class:`~weftlyflow.credentials.types.zoom_api.ZoomApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``list_meetings``, ``get_meeting``, ``create_meeting``,
  ``update_meeting``, ``delete_meeting``, ``list_past_participants``.
* ``user_id`` — Zoom user (email or user ID; ``me`` for token owner).
* ``meeting_id`` — target meeting (numeric or UUID).
* ``topic`` / ``type`` / ``start_time`` / ``duration`` / ``timezone`` /
  ``agenda`` / ``password`` / ``settings`` — create inputs.
* ``document`` — JSON patch for update.
* ``occurrence_id`` — single-occurrence delete.
* ``list_type`` / ``page_size`` / ``next_page_token`` — list paging.

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
from weftlyflow.nodes.integrations.zoom.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_MEETING,
    OP_DELETE_MEETING,
    OP_GET_MEETING,
    OP_LIST_MEETINGS,
    OP_LIST_PAST_PARTICIPANTS,
    OP_UPDATE_MEETING,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.zoom.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "zoom_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.zoom_api",)
_MEETING_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_MEETING, OP_UPDATE_MEETING, OP_DELETE_MEETING, OP_LIST_PAST_PARTICIPANTS},
)
_USER_OPERATIONS: frozenset[str] = frozenset({OP_LIST_MEETINGS, OP_CREATE_MEETING})
_PAGED_OPERATIONS: frozenset[str] = frozenset(
    {OP_LIST_MEETINGS, OP_LIST_PAST_PARTICIPANTS},
)

log = structlog.get_logger(__name__)


class ZoomNode(BaseNode):
    """Dispatch a single Zoom Meetings REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.zoom",
        version=1,
        display_name="Zoom",
        description="Manage Zoom meetings via the v2 API.",
        icon="icons/zoom.svg",
        category=NodeCategory.INTEGRATION,
        group=["communication", "meetings"],
        documentation_url="https://developers.zoom.us/docs/api/meetings/",
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
                default=OP_LIST_MEETINGS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_MEETINGS, label="List Meetings"),
                    PropertyOption(value=OP_GET_MEETING, label="Get Meeting"),
                    PropertyOption(value=OP_CREATE_MEETING, label="Create Meeting"),
                    PropertyOption(value=OP_UPDATE_MEETING, label="Update Meeting"),
                    PropertyOption(value=OP_DELETE_MEETING, label="Delete Meeting"),
                    PropertyOption(
                        value=OP_LIST_PAST_PARTICIPANTS,
                        label="List Past Participants",
                    ),
                ],
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                default="me",
                description="Zoom user ID or email ('me' for token owner).",
                display_options=DisplayOptions(
                    show={"operation": list(_USER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="meeting_id",
                display_name="Meeting ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_MEETING_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="topic",
                display_name="Topic",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_MEETING]}),
            ),
            PropertySchema(
                name="type",
                display_name="Meeting Type",
                type="number",
                description="1=instant, 2=scheduled, 3=recurring (no fixed), 8=recurring fixed.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_MEETING]}),
            ),
            PropertySchema(
                name="start_time",
                display_name="Start Time",
                type="string",
                description="ISO 8601 UTC (e.g. 2026-05-01T10:00:00Z).",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_MEETING]}),
            ),
            PropertySchema(
                name="duration",
                display_name="Duration (minutes)",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_MEETING]}),
            ),
            PropertySchema(
                name="timezone",
                display_name="Timezone",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_MEETING]}),
            ),
            PropertySchema(
                name="agenda",
                display_name="Agenda",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_MEETING]}),
            ),
            PropertySchema(
                name="password",
                display_name="Password",
                type="string",
                type_options={"password": True},
                display_options=DisplayOptions(show={"operation": [OP_CREATE_MEETING]}),
            ),
            PropertySchema(
                name="settings",
                display_name="Settings",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_MEETING]}),
            ),
            PropertySchema(
                name="document",
                display_name="Patch",
                type="json",
                description="Partial JSON patch for update.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_MEETING]}),
            ),
            PropertySchema(
                name="occurrence_id",
                display_name="Occurrence ID",
                type="string",
                description="Single-occurrence recurring-meeting target.",
                display_options=DisplayOptions(show={"operation": [OP_DELETE_MEETING]}),
            ),
            PropertySchema(
                name="list_type",
                display_name="List Type",
                type="string",
                description="scheduled, live, upcoming, upcoming_meetings, previous_meetings.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_MEETINGS]}),
            ),
            PropertySchema(
                name="page_size",
                display_name="Page Size",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": list(_PAGED_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="next_page_token",
                display_name="Next Page Token",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_PAGED_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Zoom REST call per input item."""
        access_token = await _resolve_credential(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
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
                        headers=headers,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credential(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Zoom: a zoom_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Zoom: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_MEETINGS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Zoom: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers = dict(headers)
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers=request_headers,
        )
    except httpx.HTTPError as exc:
        logger.error("zoom.request_failed", operation=operation, error=str(exc))
        msg = f"Zoom: network error on {operation}: {exc}"
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
            "zoom.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Zoom {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("zoom.ok", operation=operation, status=response.status_code)
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
        message = payload.get("message")
        if isinstance(message, str) and message:
            code = payload.get("code")
            if isinstance(code, int):
                return f"code {code}: {message}"
            return message
    return f"HTTP {status_code}"
