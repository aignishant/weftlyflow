"""Supabase node — PostgREST-backed row CRUD over a Supabase project.

Dispatches to ``<project_url>/rest/v1`` with the distinctive dual-header
auth scheme ``apikey`` + ``Authorization: Bearer`` (same key in both)
sourced from
:class:`~weftlyflow.credentials.types.supabase_api.SupabaseApiCredential`.
The project URL is part of the credential (every project lives at its
own subdomain) and is normalized via
:func:`weftlyflow.credentials.types.supabase_api.project_url_from`.

Parameters (all expression-capable):

* ``operation`` — ``select``, ``insert``, ``update``, ``delete``,
  ``upsert``.
* ``table`` — Postgres table name (required).
* ``filters`` — JSON of column → ``op.value`` string (e.g.
  ``{"id": "eq.1", "age": "gte.18"}``); bare values are coerced to
  ``eq.<value>``.
* ``rows`` — JSON object or list for insert/upsert.
* ``fields`` — JSON object of columns to patch for update.
* ``select`` / ``order`` / ``limit`` / ``offset`` — read controls.
* ``on_conflict`` — target column(s) for upsert conflict resolution.
* ``return_representation`` — when true, asks PostgREST to echo
  affected rows via the ``Prefer: return=representation`` header.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` (plus a convenience ``data`` list for read-back
operations).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.supabase_api import project_url_from
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
from weftlyflow.nodes.integrations.supabase.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_DELETE,
    OP_INSERT,
    OP_SELECT,
    OP_UPDATE,
    OP_UPSERT,
    RESOLUTION_MERGE,
    RETURN_REPRESENTATION,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.supabase.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "supabase_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.supabase_api",)
_WRITE_OPERATIONS: frozenset[str] = frozenset(
    {OP_INSERT, OP_UPDATE, OP_DELETE, OP_UPSERT},
)
_FILTER_OPERATIONS: frozenset[str] = frozenset({OP_SELECT, OP_UPDATE, OP_DELETE})
_ROWS_OPERATIONS: frozenset[str] = frozenset({OP_INSERT, OP_UPSERT})

log = structlog.get_logger(__name__)


class SupabaseNode(BaseNode):
    """Dispatch a single Supabase PostgREST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.supabase",
        version=1,
        display_name="Supabase",
        description="Read and write rows in a Supabase project via PostgREST.",
        icon="icons/supabase.svg",
        category=NodeCategory.INTEGRATION,
        group=["database", "postgres"],
        documentation_url="https://supabase.com/docs/guides/database/api",
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
                default=OP_SELECT,
                required=True,
                options=[
                    PropertyOption(value=OP_SELECT, label="Select"),
                    PropertyOption(value=OP_INSERT, label="Insert"),
                    PropertyOption(value=OP_UPDATE, label="Update"),
                    PropertyOption(value=OP_DELETE, label="Delete"),
                    PropertyOption(value=OP_UPSERT, label="Upsert"),
                ],
            ),
            PropertySchema(
                name="table",
                display_name="Table",
                type="string",
                required=True,
                description="Postgres table name (must be exposed via PostgREST).",
            ),
            PropertySchema(
                name="filters",
                display_name="Filters",
                type="json",
                description=(
                    "Column → operator-value map, e.g. "
                    "{'id': 'eq.1', 'age': 'gte.18'}. Bare values become 'eq.<v>'."
                ),
                display_options=DisplayOptions(
                    show={"operation": list(_FILTER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="rows",
                display_name="Rows",
                type="json",
                description="JSON object or list of objects to insert/upsert.",
                display_options=DisplayOptions(
                    show={"operation": list(_ROWS_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="fields",
                display_name="Fields",
                type="json",
                description="Columns → new value map for update.",
                display_options=DisplayOptions(show={"operation": [OP_UPDATE]}),
            ),
            PropertySchema(
                name="select",
                display_name="Select",
                type="string",
                description="Comma-separated columns to return (default: *).",
                display_options=DisplayOptions(show={"operation": [OP_SELECT]}),
            ),
            PropertySchema(
                name="order",
                display_name="Order",
                type="string",
                description="Column ordering, e.g. 'created_at.desc'.",
                display_options=DisplayOptions(show={"operation": [OP_SELECT]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_SELECT]}),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_SELECT]}),
            ),
            PropertySchema(
                name="on_conflict",
                display_name="On Conflict",
                type="string",
                description="Column name(s) for upsert conflict target.",
                display_options=DisplayOptions(show={"operation": [OP_UPSERT]}),
            ),
            PropertySchema(
                name="return_representation",
                display_name="Return Representation",
                type="boolean",
                default=True,
                description=(
                    "When true, ask PostgREST to echo affected rows back."
                ),
                display_options=DisplayOptions(
                    show={"operation": list(_WRITE_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Supabase PostgREST call per input item."""
        key, project_url = await _resolve_credentials(ctx)
        try:
            base_url = project_url_from(project_url)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, key=key, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Supabase: a supabase_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    key = str(payload.get("service_role_key") or "").strip()
    if not key:
        msg = "Supabase: credential has an empty 'service_role_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    project_url = str(payload.get("project_url") or "").strip()
    if not project_url:
        msg = "Supabase: credential has an empty 'project_url'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return key, project_url


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    key: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SELECT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Supabase: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers = _build_headers(
        key=key, operation=operation,
        return_representation=bool(params.get("return_representation", True)),
    )
    try:
        response = await client.request(
            method, path, params=query or None, json=body, headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.error("supabase.request_failed", operation=operation, error=str(exc))
        msg = f"Supabase: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if isinstance(payload, list):
        result["data"] = payload
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "supabase.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Supabase {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("supabase.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _build_headers(
    *,
    key: str,
    operation: str,
    return_representation: bool,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    prefer: list[str] = []
    if operation in _WRITE_OPERATIONS and return_representation:
        prefer.append(RETURN_REPRESENTATION)
    if operation == OP_UPSERT:
        prefer.append(RESOLUTION_MERGE)
    if prefer:
        headers["Prefer"] = ",".join(prefer)
    return headers


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
            details = payload.get("details")
            if isinstance(details, str) and details:
                return f"{message}: {details}"
            return message
        hint = payload.get("hint")
        if isinstance(hint, str) and hint:
            return hint
    return f"HTTP {status_code}"
