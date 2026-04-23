"""Datadog node — events, monitors, and metric queries via the Datadog API.

Dispatches to the per-site Datadog host (resolved from the credential)
with the distinctive ``DD-API-KEY`` + ``DD-APPLICATION-KEY`` header
pair sourced from
:class:`~weftlyflow.credentials.types.datadog_api.DatadogApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``post_event``, ``list_events``, ``get_monitor``,
  ``list_monitors``, ``query_metrics``, ``submit_metric``.
* ``title`` / ``text`` / ``alert_type`` / ``priority`` /
  ``source_type_name`` / ``aggregation_key`` / ``tags`` — event body.
* ``start`` / ``end`` / ``sources`` / ``unaggregated`` — event
  listing filters.
* ``monitor_id`` / ``group_states`` — single-monitor read.
* ``name`` / ``monitor_tags`` / ``page`` / ``page_size`` — monitor
  list filters.
* ``query`` / ``from_ts`` / ``to_ts`` — metric query window.
* ``metric`` / ``metric_type`` / ``points`` / ``unit`` — metric
  submission payload.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.datadog_api import site_host_from
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
from weftlyflow.nodes.integrations.datadog.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_GET_MONITOR,
    OP_LIST_EVENTS,
    OP_LIST_MONITORS,
    OP_POST_EVENT,
    OP_QUERY_METRICS,
    OP_SUBMIT_METRIC,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.datadog.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "datadog_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.datadog_api",)
_API_KEY_HEADER: str = "DD-API-KEY"
_APP_KEY_HEADER: str = "DD-APPLICATION-KEY"

log = structlog.get_logger(__name__)


class DatadogNode(BaseNode):
    """Dispatch a single Datadog API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.datadog",
        version=1,
        display_name="Datadog",
        description="Post events, read monitors, and query/submit metrics.",
        icon="icons/datadog.svg",
        category=NodeCategory.INTEGRATION,
        group=["observability", "monitoring"],
        documentation_url="https://docs.datadoghq.com/api/latest/",
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
                default=OP_POST_EVENT,
                required=True,
                options=[
                    PropertyOption(value=OP_POST_EVENT, label="Post Event"),
                    PropertyOption(value=OP_LIST_EVENTS, label="List Events"),
                    PropertyOption(value=OP_GET_MONITOR, label="Get Monitor"),
                    PropertyOption(value=OP_LIST_MONITORS, label="List Monitors"),
                    PropertyOption(value=OP_QUERY_METRICS, label="Query Metrics"),
                    PropertyOption(value=OP_SUBMIT_METRIC, label="Submit Metric"),
                ],
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_POST_EVENT]}),
            ),
            PropertySchema(
                name="text",
                display_name="Text",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_POST_EVENT]}),
            ),
            PropertySchema(
                name="alert_type",
                display_name="Alert Type",
                type="string",
                description="error, warning, info, success, ...",
                display_options=DisplayOptions(show={"operation": [OP_POST_EVENT]}),
            ),
            PropertySchema(
                name="priority",
                display_name="Priority",
                type="string",
                description="normal or low.",
                display_options=DisplayOptions(
                    show={"operation": [OP_POST_EVENT, OP_LIST_EVENTS]},
                ),
            ),
            PropertySchema(
                name="source_type_name",
                display_name="Source",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_POST_EVENT]}),
            ),
            PropertySchema(
                name="aggregation_key",
                display_name="Aggregation Key",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_POST_EVENT]}),
            ),
            PropertySchema(
                name="tags",
                display_name="Tags",
                type="string",
                description="Comma-separated or list (e.g. 'env:prod,service:api').",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_POST_EVENT,
                            OP_LIST_EVENTS,
                            OP_SUBMIT_METRIC,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="start",
                display_name="Start (Unix seconds)",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_EVENTS]}),
            ),
            PropertySchema(
                name="end",
                display_name="End (Unix seconds)",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_EVENTS]}),
            ),
            PropertySchema(
                name="sources",
                display_name="Sources",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_EVENTS]}),
            ),
            PropertySchema(
                name="unaggregated",
                display_name="Unaggregated",
                type="boolean",
                display_options=DisplayOptions(show={"operation": [OP_LIST_EVENTS]}),
            ),
            PropertySchema(
                name="monitor_id",
                display_name="Monitor ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_GET_MONITOR]}),
            ),
            PropertySchema(
                name="group_states",
                display_name="Group States",
                type="string",
                description="all, alert, warn, no data.",
                display_options=DisplayOptions(show={"operation": [OP_GET_MONITOR]}),
            ),
            PropertySchema(
                name="name",
                display_name="Name Filter",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_MONITORS]}),
            ),
            PropertySchema(
                name="monitor_tags",
                display_name="Monitor Tags",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_MONITORS]}),
            ),
            PropertySchema(
                name="page",
                display_name="Page",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_MONITORS]}),
            ),
            PropertySchema(
                name="page_size",
                display_name="Page Size",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_MONITORS]}),
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="string",
                description="Metric query DSL (e.g. avg:system.cpu.user{*}).",
                display_options=DisplayOptions(show={"operation": [OP_QUERY_METRICS]}),
            ),
            PropertySchema(
                name="from_ts",
                display_name="From (Unix seconds)",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_QUERY_METRICS]}),
            ),
            PropertySchema(
                name="to_ts",
                display_name="To (Unix seconds)",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_QUERY_METRICS]}),
            ),
            PropertySchema(
                name="metric",
                display_name="Metric Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SUBMIT_METRIC]}),
            ),
            PropertySchema(
                name="metric_type",
                display_name="Metric Type",
                type="string",
                default="gauge",
                description="gauge, count, rate, unspecified.",
                display_options=DisplayOptions(show={"operation": [OP_SUBMIT_METRIC]}),
            ),
            PropertySchema(
                name="points",
                display_name="Points",
                type="json",
                description='[{"timestamp": 1700000000, "value": 1.0}, ...]',
                display_options=DisplayOptions(show={"operation": [OP_SUBMIT_METRIC]}),
            ),
            PropertySchema(
                name="unit",
                display_name="Unit",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SUBMIT_METRIC]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Datadog API call per input item."""
        api_key, app_key, raw_site = await _resolve_credentials(ctx)
        try:
            base_url = site_host_from(raw_site)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            _API_KEY_HEADER: api_key,
            "Accept": "application/json",
        }
        if app_key:
            headers[_APP_KEY_HEADER] = app_key
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
                        headers=headers,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Datadog: a datadog_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "Datadog: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    site = str(payload.get("site") or "").strip()
    if not site:
        msg = "Datadog: credential has an empty 'site'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return api_key, str(payload.get("application_key") or "").strip(), site


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_POST_EVENT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Datadog: unsupported operation {operation!r}"
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
        logger.error("datadog.request_failed", operation=operation, error=str(exc))
        msg = f"Datadog: network error on {operation}: {exc}"
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
            "datadog.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Datadog {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("datadog.ok", operation=operation, status=response.status_code)
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
            parts = [str(err) for err in errors if err]
            if parts:
                return "; ".join(parts)
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
