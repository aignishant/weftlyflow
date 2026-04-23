"""Salesforce node — sobjects REST + SOQL query over a per-org instance URL.

Dispatches to the credential-owned ``instance_url`` (each Salesforce
org lives at its own ``https://<myDomain>.my.salesforce.com`` host) with
``Authorization: Bearer <access_token>``. The per-org base URL coming
*from* the credential — not hardcoded — is the distinctive shape.

Parameters (all expression-capable):

* ``operation`` — ``list_records`` (SOQL translation), ``get_record``,
  ``create_record``, ``update_record``, ``delete_record``, ``query``
  (raw SOQL).
* ``sobject`` — object API name (``Account``, ``Contact``, ``Opportunity``,
  or any custom ``Foo__c``).
* ``record_id`` — 15/18-char Salesforce ID for get/update/delete.
* ``document`` — field payload for create/update.
* ``fields`` / ``where`` / ``order_by`` / ``limit`` — list paging.
* ``soql`` — raw SOQL string for ``query``.
* ``api_version`` — override the default ``v58.0``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.salesforce_api import instance_url_from
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
from weftlyflow.nodes.integrations.salesforce.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_RECORD,
    OP_DELETE_RECORD,
    OP_GET_RECORD,
    OP_LIST_RECORDS,
    OP_QUERY,
    OP_UPDATE_RECORD,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.salesforce.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "salesforce_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.salesforce_api",)
_RECORD_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_RECORD, OP_UPDATE_RECORD, OP_DELETE_RECORD},
)
_DOCUMENT_OPERATIONS: frozenset[str] = frozenset({OP_CREATE_RECORD, OP_UPDATE_RECORD})
_SOBJECT_OPERATIONS: frozenset[str] = frozenset(
    {
        OP_LIST_RECORDS,
        OP_GET_RECORD,
        OP_CREATE_RECORD,
        OP_UPDATE_RECORD,
        OP_DELETE_RECORD,
    },
)

log = structlog.get_logger(__name__)


class SalesforceNode(BaseNode):
    """Dispatch a single Salesforce REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.salesforce",
        version=1,
        display_name="Salesforce",
        description="Query and mutate Salesforce sobjects via REST.",
        icon="icons/salesforce.svg",
        category=NodeCategory.INTEGRATION,
        group=["crm", "sales"],
        documentation_url=(
            "https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/"
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
                default=OP_LIST_RECORDS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_RECORDS, label="List Records"),
                    PropertyOption(value=OP_GET_RECORD, label="Get Record"),
                    PropertyOption(value=OP_CREATE_RECORD, label="Create Record"),
                    PropertyOption(value=OP_UPDATE_RECORD, label="Update Record"),
                    PropertyOption(value=OP_DELETE_RECORD, label="Delete Record"),
                    PropertyOption(value=OP_QUERY, label="SOQL Query"),
                ],
            ),
            PropertySchema(
                name="sobject",
                display_name="SObject",
                type="string",
                description="API name (Account, Contact, Foo__c).",
                display_options=DisplayOptions(
                    show={"operation": list(_SOBJECT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="record_id",
                display_name="Record ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_RECORD_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="document",
                display_name="Fields",
                type="json",
                description="Field payload for create/update.",
                display_options=DisplayOptions(
                    show={"operation": list(_DOCUMENT_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="string",
                description="Comma-separated field API names to select.",
                display_options=DisplayOptions(
                    show={"operation": [OP_LIST_RECORDS, OP_GET_RECORD]},
                ),
            ),
            PropertySchema(
                name="where",
                display_name="Where",
                type="string",
                description="SOQL WHERE clause (without the keyword).",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="order_by",
                display_name="Order By",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="soql",
                display_name="SOQL",
                type="string",
                description="Raw SOQL query string.",
                display_options=DisplayOptions(show={"operation": [OP_QUERY]}),
            ),
            PropertySchema(
                name="api_version",
                display_name="API Version",
                type="string",
                description="Override the default v58.0.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Salesforce REST call per input item."""
        access_token, raw_instance = await _resolve_credentials(ctx)
        try:
            base_url = instance_url_from(raw_instance)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
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


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Salesforce: a salesforce_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Salesforce: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    instance_url = str(payload.get("instance_url") or "").strip()
    if not instance_url:
        msg = "Salesforce: credential has an empty 'instance_url'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, instance_url


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_RECORDS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Salesforce: unsupported operation {operation!r}"
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
        logger.error("salesforce.request_failed", operation=operation, error=str(exc))
        msg = f"Salesforce: network error on {operation}: {exc}"
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
            "salesforce.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Salesforce {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("salesforce.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            code = first.get("errorCode")
            message = first.get("message")
            if isinstance(code, str) and isinstance(message, str):
                return f"{code}: {message}"
            if isinstance(message, str) and message:
                return message
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str) and error:
            description = payload.get("error_description")
            if isinstance(description, str) and description:
                return f"{error}: {description}"
            return error
    return f"HTTP {status_code}"
