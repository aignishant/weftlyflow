"""PagerDuty node — REST v2 API for incident management.

Dispatches to ``https://api.pagerduty.com/...`` with the distinctive
``Authorization: Token token=<key>`` auth header (no ``Bearer`` prefix)
sourced from
:class:`~weftlyflow.credentials.types.pagerduty_api.PagerDutyApiCredential`.
Mutating calls require a ``From: <admin_email>`` header; the credential
may supply a default, and the node layer lets callers override it
per-execution via the ``from_email`` parameter.

Parameters (all expression-capable):

* ``operation`` — ``list_incidents``, ``get_incident``,
  ``create_incident``, ``update_incident``, ``add_note``.
* ``incident_id`` — for get/update/add_note.
* ``title`` / ``service_id`` / ``urgency`` / ``body`` — for
  ``create_incident``.
* ``fields`` — JSON of updates for ``update_incident``.
* ``content`` — note body for ``add_note``.
* ``statuses`` / ``urgencies`` / ``service_ids`` / ``limit`` / ``offset``
  — list filters.
* ``from_email`` — overrides the credential's ``From`` header.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``; ``list_incidents`` also surfaces a convenience
``incidents`` list.
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
from weftlyflow.nodes.integrations.pagerduty.constants import (
    ACCEPT_HEADER,
    API_BASE_URL,
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_ADD_NOTE,
    OP_CREATE_INCIDENT,
    OP_GET_INCIDENT,
    OP_LIST_INCIDENTS,
    OP_UPDATE_INCIDENT,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.pagerduty.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "pagerduty_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.pagerduty_api",)
_INCIDENT_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_INCIDENT, OP_UPDATE_INCIDENT, OP_ADD_NOTE},
)
_MUTATING_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_INCIDENT, OP_UPDATE_INCIDENT, OP_ADD_NOTE},
)

log = structlog.get_logger(__name__)


class PagerDutyNode(BaseNode):
    """Dispatch a single PagerDuty REST v2 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.pagerduty",
        version=1,
        display_name="PagerDuty",
        description="Manage PagerDuty incidents via the REST v2 API.",
        icon="icons/pagerduty.svg",
        category=NodeCategory.INTEGRATION,
        group=["devops", "alerting"],
        documentation_url="https://developer.pagerduty.com/api-reference/",
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
                default=OP_LIST_INCIDENTS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_INCIDENTS, label="List Incidents"),
                    PropertyOption(value=OP_GET_INCIDENT, label="Get Incident"),
                    PropertyOption(value=OP_CREATE_INCIDENT, label="Create Incident"),
                    PropertyOption(value=OP_UPDATE_INCIDENT, label="Update Incident"),
                    PropertyOption(value=OP_ADD_NOTE, label="Add Note"),
                ],
            ),
            PropertySchema(
                name="incident_id",
                display_name="Incident ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_INCIDENT_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_INCIDENT]}),
            ),
            PropertySchema(
                name="service_id",
                display_name="Service ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_INCIDENT]}),
            ),
            PropertySchema(
                name="urgency",
                display_name="Urgency",
                type="options",
                options=[
                    PropertyOption(value="high", label="High"),
                    PropertyOption(value="low", label="Low"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_CREATE_INCIDENT]}),
            ),
            PropertySchema(
                name="body",
                display_name="Incident Details",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_INCIDENT]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="Fields to patch (status, priority, resolution...).",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_INCIDENT]}),
            ),
            PropertySchema(
                name="content",
                display_name="Note Content",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_ADD_NOTE]}),
            ),
            PropertySchema(
                name="statuses",
                display_name="Statuses",
                type="string",
                description="Comma-separated triggered/acknowledged/resolved.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_INCIDENTS]}),
            ),
            PropertySchema(
                name="urgencies",
                display_name="Urgencies",
                type="string",
                description="Comma-separated high/low.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_INCIDENTS]}),
            ),
            PropertySchema(
                name="service_ids",
                display_name="Service IDs",
                type="string",
                description="Comma-separated PagerDuty service IDs.",
                display_options=DisplayOptions(show={"operation": [OP_LIST_INCIDENTS]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                default=DEFAULT_LIST_LIMIT,
                display_options=DisplayOptions(show={"operation": [OP_LIST_INCIDENTS]}),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_INCIDENTS]}),
            ),
            PropertySchema(
                name="from_email",
                display_name="From Email",
                type="string",
                description="Overrides the credential's From header.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one PagerDuty REST call per input item."""
        key, default_from = await _resolve_credentials(ctx)
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
                        key=key,
                        default_from=default_from,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "PagerDuty: a pagerduty_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    key = str(payload.get("api_key") or "").strip()
    if not key:
        msg = "PagerDuty: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    default_from = str(payload.get("from_email") or "").strip()
    return key, default_from


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    key: str,
    default_from: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_INCIDENTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"PagerDuty: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers: dict[str, str] = {
        "Authorization": f"Token token={key}",
        "Accept": ACCEPT_HEADER,
        "Content-Type": "application/json",
    }
    override_from = str(params.get("from_email") or "").strip()
    from_email = override_from or default_from
    if operation in _MUTATING_OPERATIONS:
        if not from_email:
            msg = f"PagerDuty: '{operation}' requires a 'from_email' (header or credential)"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        headers["From"] = from_email
    elif from_email:
        headers["From"] = from_email
    try:
        response = await client.request(
            method, path, params=query or None, json=body, headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.error("pagerduty.request_failed", operation=operation, error=str(exc))
        msg = f"PagerDuty: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_INCIDENTS and isinstance(payload, dict):
        incidents = payload.get("incidents", [])
        result["incidents"] = incidents if isinstance(incidents, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "pagerduty.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"PagerDuty {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("pagerduty.ok", operation=operation, status=response.status_code)
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
            errors_list = error.get("errors")
            if isinstance(errors_list, list) and errors_list:
                joined = "; ".join(str(e) for e in errors_list)
                return f"{message}: {joined}" if message else joined
            if isinstance(message, str) and message:
                return message
        elif isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"
