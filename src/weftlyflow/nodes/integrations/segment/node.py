"""Segment node — Track/Identify/Group/Page/Alias event ingestion.

Dispatches to ``https://api.segment.io/v1/*`` with the source write key
supplied by :class:`~weftlyflow.credentials.types.segment_write_key.SegmentWriteKeyCredential`
— HTTP Basic auth where the write key is the username and the password
is empty. The node itself is a thin transport; all body shaping lives
in :mod:`weftlyflow.nodes.integrations.segment.operations`.

Parameters (all expression-capable):

* ``operation`` — ``track`` | ``identify`` | ``group`` | ``page`` | ``alias``.
* ``userId`` / ``anonymousId`` — identity; at least one is required.
* ``event`` — required for ``track``.
* ``groupId`` — required for ``group``.
* ``previousId`` — required for ``alias``.
* ``properties`` / ``traits`` / ``context`` / ``timestamp`` / ``name`` /
  ``category`` — verb-specific enrichment.

Output: one item per input item with ``operation``, ``status``, and
the parsed JSON ``response`` (Segment returns ``{"success": true}``).
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
from weftlyflow.nodes.integrations.segment.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ALIAS,
    OP_GROUP,
    OP_IDENTIFY,
    OP_PAGE,
    OP_TRACK,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.segment.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "segment_write_key"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.segment_write_key",)

log = structlog.get_logger(__name__)


class SegmentNode(BaseNode):
    """Dispatch a single Segment ingestion call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.segment",
        version=1,
        display_name="Segment",
        description="Track, identify, group, page, and alias via the Segment HTTP API.",
        icon="icons/segment.svg",
        category=NodeCategory.INTEGRATION,
        group=["analytics"],
        documentation_url=(
            "https://segment.com/docs/connections/sources/catalog/libraries/server/http-api/"
        ),
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
                default=OP_TRACK,
                required=True,
                options=[
                    PropertyOption(value=OP_TRACK, label="Track"),
                    PropertyOption(value=OP_IDENTIFY, label="Identify"),
                    PropertyOption(value=OP_GROUP, label="Group"),
                    PropertyOption(value=OP_PAGE, label="Page"),
                    PropertyOption(value=OP_ALIAS, label="Alias"),
                ],
            ),
            PropertySchema(
                name="userId",
                display_name="User ID",
                type="string",
                description="Known user id — required if 'anonymousId' is absent.",
            ),
            PropertySchema(
                name="anonymousId",
                display_name="Anonymous ID",
                type="string",
                description="Pre-login id — required if 'userId' is absent.",
            ),
            PropertySchema(
                name="event",
                display_name="Event Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_TRACK]}),
            ),
            PropertySchema(
                name="groupId",
                display_name="Group ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_GROUP]}),
            ),
            PropertySchema(
                name="previousId",
                display_name="Previous ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_ALIAS]}),
            ),
            PropertySchema(
                name="properties",
                display_name="Properties",
                type="json",
                display_options=DisplayOptions(
                    show={"operation": [OP_TRACK, OP_PAGE]},
                ),
            ),
            PropertySchema(
                name="traits",
                display_name="Traits",
                type="json",
                display_options=DisplayOptions(
                    show={"operation": [OP_IDENTIFY, OP_GROUP]},
                ),
            ),
            PropertySchema(
                name="name",
                display_name="Page Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_PAGE]}),
            ),
            PropertySchema(
                name="category",
                display_name="Page Category",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_PAGE]}),
            ),
            PropertySchema(
                name="context",
                display_name="Context",
                type="json",
                description="Optional Segment 'context' envelope merged into the body.",
            ),
            PropertySchema(
                name="timestamp",
                display_name="Timestamp (ISO-8601)",
                type="string",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Segment call per input item."""
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
                        ctx, item,
                        client=client, injector=injector,
                        creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Segment: a segment_write_key credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("write_key") or "").strip():
        msg = "Segment: credential has an empty 'write_key'"
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
    operation = str(params.get("operation") or OP_TRACK).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Segment: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = client.build_request(
        method, path, params=query or None, json=body,
        headers={"Accept": "application/json"},
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("segment.request_failed", operation=operation, error=str(exc))
        msg = f"Segment: network error on {operation}: {exc}"
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
            "segment.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Segment {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("segment.ok", operation=operation, status=response.status_code)
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
        for key in ("message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
