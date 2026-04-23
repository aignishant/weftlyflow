"""PostHog node — capture, batch, identify, alias, decide.

Dispatches against the configured PostHog host (default
``https://us.i.posthog.com``; EU cloud and self-hosted supported via
credential field). The project API key is carried **inside the JSON
body** under ``api_key`` — see
:class:`~weftlyflow.credentials.types.posthog_api.PostHogApiCredential`
for background. The node is the single place that folds ``api_key``
into the body so the operation builders remain credential-free.

Parameters (all expression-capable):

* ``operation`` — ``capture`` | ``identify`` | ``alias`` | ``batch`` | ``decide``.
* ``event`` / ``distinct_id`` / ``properties`` / ``timestamp`` — capture.
* ``set`` / ``set_once`` — identify trait envelopes.
* ``alias`` — the secondary identity being aliased on ``alias``.
* ``events`` — required list for ``batch``.
* ``groups`` / ``person_properties`` — optional feature-flag inputs.

Output: one item per input item with ``operation``, ``status``, and the
parsed JSON ``response``.
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
from weftlyflow.nodes.integrations.posthog.constants import (
    DEFAULT_HOST,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ALIAS,
    OP_BATCH,
    OP_CAPTURE,
    OP_DECIDE,
    OP_IDENTIFY,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.posthog.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "posthog_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.posthog_api",)

log = structlog.get_logger(__name__)


class PostHogNode(BaseNode):
    """Dispatch a single PostHog API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.posthog",
        version=1,
        display_name="PostHog",
        description="Capture events, batch-ingest, identify users, and evaluate feature flags.",
        icon="icons/posthog.svg",
        category=NodeCategory.INTEGRATION,
        group=["analytics"],
        documentation_url="https://posthog.com/docs/api",
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
                default=OP_CAPTURE,
                required=True,
                options=[
                    PropertyOption(value=OP_CAPTURE, label="Capture Event"),
                    PropertyOption(value=OP_IDENTIFY, label="Identify User"),
                    PropertyOption(value=OP_ALIAS, label="Alias"),
                    PropertyOption(value=OP_BATCH, label="Batch Ingest"),
                    PropertyOption(value=OP_DECIDE, label="Decide (Feature Flags)"),
                ],
            ),
            PropertySchema(
                name="distinct_id",
                display_name="Distinct ID",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_CAPTURE, OP_IDENTIFY, OP_ALIAS, OP_DECIDE],
                    },
                ),
            ),
            PropertySchema(
                name="event",
                display_name="Event Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CAPTURE]}),
            ),
            PropertySchema(
                name="alias",
                display_name="Alias ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_ALIAS]}),
            ),
            PropertySchema(
                name="properties",
                display_name="Properties",
                type="json",
                display_options=DisplayOptions(
                    show={"operation": [OP_CAPTURE, OP_IDENTIFY, OP_ALIAS]},
                ),
            ),
            PropertySchema(
                name="set",
                display_name="$set Traits",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_IDENTIFY]}),
            ),
            PropertySchema(
                name="set_once",
                display_name="$set_once Traits",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_IDENTIFY]}),
            ),
            PropertySchema(
                name="events",
                display_name="Events (array)",
                type="json",
                description="Array of event dicts for /batch.",
                display_options=DisplayOptions(show={"operation": [OP_BATCH]}),
            ),
            PropertySchema(
                name="groups",
                display_name="Groups",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_DECIDE]}),
            ),
            PropertySchema(
                name="person_properties",
                display_name="Person Properties",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_DECIDE]}),
            ),
            PropertySchema(
                name="timestamp",
                display_name="Timestamp (ISO-8601)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CAPTURE, OP_IDENTIFY, OP_ALIAS]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one PostHog call per input item."""
        payload = await _resolve_credentials(ctx)
        host = str(payload.get("host") or DEFAULT_HOST).rstrip("/")
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=host, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> dict[str, Any]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "PostHog: a posthog_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _injector, payload = credential
    if not str(payload.get("project_api_key") or "").strip():
        msg = "PostHog: credential has an empty 'project_api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_CAPTURE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"PostHog: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    body = _fold_api_key(body, creds["project_api_key"])
    request = client.build_request(
        method, path, params=query or None, json=body,
        headers={"Accept": "application/json"},
    )
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("posthog.request_failed", operation=operation, error=str(exc))
        msg = f"PostHog: network error on {operation}: {exc}"
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
            "posthog.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"PostHog {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("posthog.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _fold_api_key(body: dict[str, Any] | None, api_key: str) -> dict[str, Any]:
    out: dict[str, Any] = dict(body) if isinstance(body, dict) else {}
    out["api_key"] = api_key
    return out


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, dict):
        for key in ("detail", "error", "message"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
