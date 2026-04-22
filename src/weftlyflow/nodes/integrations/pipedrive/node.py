"""Pipedrive node — v1 REST API for deals, persons, and activities.

Dispatches to ``https://<company>.pipedrive.com/api/v1/...`` with the
API token appended as the ``api_token`` query parameter sourced from
:class:`~weftlyflow.credentials.types.pipedrive_api.PipedriveApiCredential`.
The tenant subdomain is read from the credential's ``company_domain``
field via
:func:`weftlyflow.credentials.types.pipedrive_api.base_url_for`.

Parameters (all expression-capable):

* ``operation`` — ``list_deals``, ``get_deal``, ``create_deal``,
  ``update_deal``, ``create_person``, ``create_activity``.
* ``deal_id`` — for ``get_deal`` and ``update_deal``.
* ``title`` / ``value`` / ``currency`` / ``status`` /
  ``person_id`` / ``org_id`` / ``stage_id`` / ``user_id`` —
  ``create_deal``.
* ``fields`` — JSON of updates for ``update_deal``.
* ``limit`` / ``start`` / ``owner_id`` — ``list_deals`` paging.
* ``name`` / ``emails`` / ``phones`` / ``org_id`` / ``owner_id`` —
  ``create_person``.
* ``subject`` / ``type`` / ``due_date`` / ``due_time`` /
  ``duration`` / ``note`` / ``deal_id`` / ``person_id`` —
  ``create_activity``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``. ``list_deals`` surfaces a convenience ``data`` list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.pipedrive_api import base_url_for
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
from weftlyflow.nodes.integrations.pipedrive.constants import (
    DEAL_STATUSES,
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_ACTIVITY,
    OP_CREATE_DEAL,
    OP_CREATE_PERSON,
    OP_GET_DEAL,
    OP_LIST_DEALS,
    OP_UPDATE_DEAL,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.pipedrive.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "pipedrive_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.pipedrive_api",)
_DEAL_ID_OPERATIONS: frozenset[str] = frozenset({OP_GET_DEAL, OP_UPDATE_DEAL})

log = structlog.get_logger(__name__)


class PipedriveNode(BaseNode):
    """Dispatch a single Pipedrive REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.pipedrive",
        version=1,
        display_name="Pipedrive",
        description="Manage Pipedrive deals, persons, and activities.",
        icon="icons/pipedrive.svg",
        category=NodeCategory.INTEGRATION,
        group=["crm", "sales"],
        documentation_url="https://developers.pipedrive.com/docs/api/v1/",
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
                default=OP_LIST_DEALS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_DEALS, label="List Deals"),
                    PropertyOption(value=OP_GET_DEAL, label="Get Deal"),
                    PropertyOption(value=OP_CREATE_DEAL, label="Create Deal"),
                    PropertyOption(value=OP_UPDATE_DEAL, label="Update Deal"),
                    PropertyOption(value=OP_CREATE_PERSON, label="Create Person"),
                    PropertyOption(value=OP_CREATE_ACTIVITY, label="Create Activity"),
                ],
            ),
            PropertySchema(
                name="deal_id",
                display_name="Deal ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_DEAL_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_DEAL]}),
            ),
            PropertySchema(
                name="value",
                display_name="Value",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_DEAL]}),
            ),
            PropertySchema(
                name="currency",
                display_name="Currency",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_DEAL]}),
            ),
            PropertySchema(
                name="status",
                display_name="Status",
                type="options",
                options=[
                    PropertyOption(value=value, label=value.replace("_", " ").title())
                    for value in sorted(DEAL_STATUSES)
                ],
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_DEAL, OP_LIST_DEALS]},
                ),
            ),
            PropertySchema(
                name="person_id",
                display_name="Person ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_DEAL, OP_CREATE_ACTIVITY]},
                ),
            ),
            PropertySchema(
                name="org_id",
                display_name="Organization ID",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_CREATE_DEAL, OP_CREATE_PERSON, OP_CREATE_ACTIVITY,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="stage_id",
                display_name="Stage ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_DEAL]}),
            ),
            PropertySchema(
                name="user_id",
                display_name="User ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_DEAL, OP_CREATE_ACTIVITY]},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="JSON patch body for update_deal.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_DEAL]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                default=DEFAULT_LIST_LIMIT,
                display_options=DisplayOptions(show={"operation": [OP_LIST_DEALS]}),
            ),
            PropertySchema(
                name="start",
                display_name="Start",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_DEALS]}),
            ),
            PropertySchema(
                name="owner_id",
                display_name="Owner ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_DEALS]}),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_PERSON]}),
            ),
            PropertySchema(
                name="emails",
                display_name="Emails",
                type="string",
                description="Comma-separated list of emails.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_PERSON]}),
            ),
            PropertySchema(
                name="phones",
                display_name="Phones",
                type="string",
                description="Comma-separated list of phone numbers.",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_PERSON]}),
            ),
            PropertySchema(
                name="subject",
                display_name="Subject",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ACTIVITY]}),
            ),
            PropertySchema(
                name="type",
                display_name="Activity Type",
                type="string",
                description="Pipedrive activity-type key (e.g. 'call', 'meeting').",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ACTIVITY]}),
            ),
            PropertySchema(
                name="due_date",
                display_name="Due Date",
                type="string",
                description="ISO date (YYYY-MM-DD).",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ACTIVITY]}),
            ),
            PropertySchema(
                name="due_time",
                display_name="Due Time",
                type="string",
                description="24-hour time (HH:MM).",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ACTIVITY]}),
            ),
            PropertySchema(
                name="duration",
                display_name="Duration",
                type="string",
                description="Duration (HH:MM).",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ACTIVITY]}),
            ),
            PropertySchema(
                name="note",
                display_name="Note",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_ACTIVITY]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Pipedrive REST call per input item."""
        token, company_domain = await _resolve_credentials(ctx)
        try:
            base = base_url_for(company_domain)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=base, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, token=token, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Pipedrive: a pipedrive_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("api_token") or "").strip()
    if not token:
        msg = "Pipedrive: credential has an empty 'api_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    company_domain = str(payload.get("company_domain") or "").strip()
    if not company_domain:
        msg = "Pipedrive: credential has an empty 'company_domain'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, company_domain


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_DEALS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Pipedrive: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    merged_query = dict(query)
    merged_query["api_token"] = token
    try:
        response = await client.request(
            method,
            path,
            params=merged_query,
            json=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("pipedrive.request_failed", operation=operation, error=str(exc))
        msg = f"Pipedrive: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_DEALS and isinstance(payload, dict):
        data = payload.get("data")
        result["data"] = data if isinstance(data, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "pipedrive.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Pipedrive {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("pipedrive.ok", operation=operation, status=response.status_code)
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
        if isinstance(error, str) and error:
            info = payload.get("error_info")
            return f"{error} ({info})" if info else error
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
