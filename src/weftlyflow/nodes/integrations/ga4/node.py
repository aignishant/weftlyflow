"""GA4 Measurement Protocol node — server-side event ingestion.

Dispatches against ``https://www.google-analytics.com`` with
``measurement_id`` and ``api_secret`` query parameters injected by
:class:`~weftlyflow.credentials.types.ga4_measurement.Ga4MeasurementCredential`.
Routes between ``/mp/collect`` (production) and ``/debug/mp/collect``
(validation) based on the chosen operation.

Parameters (all expression-capable):

* ``operation`` — ``track_event`` / ``track_events`` /
  ``validate_event`` / ``user_properties``.
* ``client_id`` — required; stable per-device/user identifier.
* ``user_id`` — optional signed-in user ID.
* ``event_name`` / ``event_params`` — single-event operations.
* ``events`` — list of event dicts for ``track_events``.
* ``user_properties`` — dict of properties for ``user_properties`` op.
* ``timestamp_micros`` — optional event timestamp override.
* ``non_personalized_ads`` — optional advertising opt-out.

GA4 returns 204 No Content on accepted events; the debug endpoint
returns 200 with a ``validationMessages`` array. Output exposes both
alongside ``operation`` and ``status``.
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
from weftlyflow.nodes.integrations.ga4.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_TRACK_EVENT,
    OP_TRACK_EVENTS,
    OP_USER_PROPERTIES,
    OP_VALIDATE_EVENT,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.ga4.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "ga4_measurement"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.ga4_measurement",)

log = structlog.get_logger(__name__)


class Ga4Node(BaseNode):
    """Dispatch a single GA4 Measurement Protocol call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.ga4",
        version=1,
        display_name="Google Analytics 4",
        description="Send server-side events and user properties via the GA4 Measurement Protocol.",
        icon="icons/ga4.svg",
        category=NodeCategory.INTEGRATION,
        group=["analytics"],
        documentation_url=(
            "https://developers.google.com/analytics/devguides/collection/protocol/ga4/"
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
                default=OP_TRACK_EVENT,
                required=True,
                options=[
                    PropertyOption(value=OP_TRACK_EVENT, label="Track Event"),
                    PropertyOption(value=OP_TRACK_EVENTS, label="Track Events (Batch)"),
                    PropertyOption(value=OP_VALIDATE_EVENT, label="Validate Event"),
                    PropertyOption(value=OP_USER_PROPERTIES, label="Set User Properties"),
                ],
            ),
            PropertySchema(
                name="client_id",
                display_name="Client ID",
                type="string",
                required=True,
                description="Stable per-device/user identifier (required by GA4).",
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                description="Optional signed-in user ID.",
            ),
            PropertySchema(
                name="event_name",
                display_name="Event Name",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_TRACK_EVENT, OP_VALIDATE_EVENT]},
                ),
            ),
            PropertySchema(
                name="event_params",
                display_name="Event Params",
                type="json",
                display_options=DisplayOptions(
                    show={"operation": [OP_TRACK_EVENT, OP_VALIDATE_EVENT]},
                ),
            ),
            PropertySchema(
                name="events",
                display_name="Events",
                type="json",
                description='List of event dicts, e.g. [{"name": "sign_up", "params": {...}}].',
                display_options=DisplayOptions(show={"operation": [OP_TRACK_EVENTS]}),
            ),
            PropertySchema(
                name="user_properties",
                display_name="User Properties",
                type="json",
                description="Dict of user properties (values wrapped as {value: ...}).",
                display_options=DisplayOptions(show={"operation": [OP_USER_PROPERTIES]}),
            ),
            PropertySchema(
                name="timestamp_micros",
                display_name="Timestamp (micros)",
                type="number",
                description="Optional event timestamp override in microseconds.",
            ),
            PropertySchema(
                name="non_personalized_ads",
                display_name="Non-Personalized Ads",
                type="boolean",
                description="Set to true to opt the event out of personalized advertising.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one GA4 call per input item."""
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
        msg = "GA4: a ga4_measurement credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("measurement_id") or "").strip():
        msg = "GA4: credential has an empty 'measurement_id'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not str(payload.get("api_secret") or "").strip():
        msg = "GA4: credential has an empty 'api_secret'"
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
    operation = str(params.get("operation") or OP_TRACK_EVENT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"GA4: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = client.build_request(
        method, path, params=query or None, json=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("ga4.request_failed", operation=operation, error=str(exc))
        msg = f"GA4: network error on {operation}: {exc}"
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
            "ga4.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"GA4 {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("ga4.ok", operation=operation, status=response.status_code)
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
        for key in ("error", "message"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
