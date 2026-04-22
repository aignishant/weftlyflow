"""Airtable node — list/get/create/update/delete records via the v0 REST API.

Dispatches to ``https://api.airtable.com/v0/{baseId}/{table}[/{recordId}]``.
Authenticates via ``Authorization: Bearer <token>`` from a
:class:`~weftlyflow.credentials.types.bearer_token.BearerTokenCredential`
holding a personal-access token with ``data.records:read`` +
``data.records:write`` scopes.

Parameters (all expression-capable):

* ``operation`` — ``list_records``, ``get_record``, ``create_records``,
  ``update_record``, ``delete_record``.
* ``base_id`` / ``table`` — required for every operation.
* ``record_id`` — required for get/update/delete.
* ``records`` — list of ``{"fields": {...}}`` objects for create (max 10).
* ``fields`` — object for update.
* ``view`` / ``filter_by_formula`` / ``offset`` / ``max_records`` /
  ``page_size`` — list knobs.
* ``typecast`` — optional boolean forwarded to the API.

Output: one item per input item with ``operation``, ``status``, parsed
``response`` object, plus a convenience ``records`` list for
``list_records``.
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
from weftlyflow.nodes.integrations.airtable.constants import (
    API_BASE_URL,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_RECORDS,
    OP_DELETE_RECORD,
    OP_GET_RECORD,
    OP_LIST_RECORDS,
    OP_UPDATE_RECORD,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.airtable.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "airtable_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.bearer_token",)
_RECORD_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_RECORD, OP_UPDATE_RECORD, OP_DELETE_RECORD},
)

log = structlog.get_logger(__name__)


class AirtableNode(BaseNode):
    """Dispatch a single Airtable REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.airtable",
        version=1,
        display_name="Airtable",
        description="List, get, create, update, and delete Airtable records.",
        icon="icons/airtable.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "database"],
        documentation_url="https://airtable.com/developers/web/api/introduction",
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
                    PropertyOption(value=OP_CREATE_RECORDS, label="Create Records"),
                    PropertyOption(value=OP_UPDATE_RECORD, label="Update Record"),
                    PropertyOption(value=OP_DELETE_RECORD, label="Delete Record"),
                ],
            ),
            PropertySchema(
                name="base_id",
                display_name="Base ID",
                type="string",
                required=True,
                placeholder="appXXXXXXXXXXXXXX",
            ),
            PropertySchema(
                name="table",
                display_name="Table",
                type="string",
                required=True,
                description="Table name or table id.",
            ),
            PropertySchema(
                name="record_id",
                display_name="Record ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_RECORD_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="records",
                display_name="Records",
                type="json",
                description="List of records: [{fields: {...}}, ...].",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_RECORDS]}),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE_RECORD]}),
            ),
            PropertySchema(
                name="typecast",
                display_name="Typecast",
                type="boolean",
                default=False,
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_RECORDS, OP_UPDATE_RECORD]},
                ),
            ),
            PropertySchema(
                name="view",
                display_name="View",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="filter_by_formula",
                display_name="Filter (formula)",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="page_size",
                display_name="Page Size",
                type="number",
                default=DEFAULT_PAGE_SIZE,
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="max_records",
                display_name="Max Records",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_RECORDS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Airtable REST call per input item."""
        token = await _resolve_token(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(ctx, item, client=client, token=token, logger=bound),
                )
        return [results]


async def _resolve_token(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Airtable: a bearer-token credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("token") or "").strip()
    if not token:
        msg = "Airtable: credential has an empty 'token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_RECORDS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Airtable: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("airtable.request_failed", operation=operation, error=str(exc))
        msg = f"Airtable: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_RECORDS and isinstance(payload, dict):
        records = payload.get("records", [])
        result["records"] = records if isinstance(records, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "airtable.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Airtable {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("airtable.ok", operation=operation, status=response.status_code)
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
            if isinstance(message, str) and message:
                return message
            etype = error.get("type")
            if isinstance(etype, str) and etype:
                return etype
        elif isinstance(error, str) and error:
            return error
    return f"HTTP {status_code}"
