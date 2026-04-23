"""Snowflake SQL API node — execute statements + poll async results.

Dispatches to ``<account>.snowflakecomputing.com/api/v2`` with the
distinctive Snowflake header pair: ``Authorization: Bearer <token>``
plus ``X-Snowflake-Authorization-Token-Type`` declaring whether the
Bearer is a ``KEYPAIR_JWT`` (RSA-signed JWT) or an ``OAUTH`` access
token from a Snowflake security integration. Both credentials and
base URL come from
:class:`~weftlyflow.credentials.types.snowflake_api.SnowflakeApiCredential`.

Parameters (all expression-capable):

* ``operation`` — ``execute``, ``get_status``, ``cancel``.
* ``statement`` — SQL text for ``execute``.
* ``statement_handle`` — opaque handle returned by async execute.
* ``warehouse`` / ``database`` / ``schema`` / ``role`` — session
  overrides.
* ``timeout`` — seconds the service waits for synchronous completion
  (0 = return handle immediately).
* ``bindings`` — positional binds as ``{"1": {"type": "TEXT", "value": "..."}}``.
* ``async_exec`` — force the ``async=true`` query flag.
* ``partition`` / ``page_size`` — result-set paging for ``get_status``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.snowflake_api import account_host_from
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
from weftlyflow.nodes.integrations.snowflake.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CANCEL,
    OP_EXECUTE,
    OP_GET_STATUS,
    SUPPORTED_OPERATIONS,
    TOKEN_TYPE_HEADER,
)
from weftlyflow.nodes.integrations.snowflake.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "snowflake_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.snowflake_api",)
_HANDLE_OPERATIONS: frozenset[str] = frozenset({OP_GET_STATUS, OP_CANCEL})
_VALID_TOKEN_TYPES: frozenset[str] = frozenset({"KEYPAIR_JWT", "OAUTH"})

log = structlog.get_logger(__name__)


class SnowflakeNode(BaseNode):
    """Dispatch a single Snowflake SQL API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.snowflake",
        version=1,
        display_name="Snowflake",
        description="Execute Snowflake SQL statements via the v2 SQL API.",
        icon="icons/snowflake.svg",
        category=NodeCategory.INTEGRATION,
        group=["database", "data-warehouse"],
        documentation_url=(
            "https://docs.snowflake.com/en/developer-guide/sql-api/index"
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
                default=OP_EXECUTE,
                required=True,
                options=[
                    PropertyOption(value=OP_EXECUTE, label="Execute Statement"),
                    PropertyOption(value=OP_GET_STATUS, label="Get Status / Results"),
                    PropertyOption(value=OP_CANCEL, label="Cancel Statement"),
                ],
            ),
            PropertySchema(
                name="statement",
                display_name="SQL Statement",
                type="string",
                description="SQL text to execute.",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="statement_handle",
                display_name="Statement Handle",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_HANDLE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="warehouse",
                display_name="Warehouse",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="database",
                display_name="Database",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="schema",
                display_name="Schema",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="role",
                display_name="Role",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="timeout",
                display_name="Timeout (seconds)",
                type="number",
                description="Server-side wait; 0 forces async handle return.",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="bindings",
                display_name="Bindings",
                type="json",
                description="Positional binds: {\"1\": {\"type\": \"TEXT\", \"value\": \"x\"}}.",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="async_exec",
                display_name="Force Async",
                type="boolean",
                description="Send ?async=true — always return a handle.",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="request_id",
                display_name="Request ID",
                type="string",
                description="Idempotency key for retries.",
                display_options=DisplayOptions(show={"operation": [OP_EXECUTE]}),
            ),
            PropertySchema(
                name="partition",
                display_name="Partition",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_GET_STATUS]}),
            ),
            PropertySchema(
                name="page_size",
                display_name="Page Size",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_GET_STATUS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Snowflake SQL API call per input item."""
        token, token_type, raw_account = await _resolve_credentials(ctx)
        try:
            base_url = account_host_from(raw_account)
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {token}",
            TOKEN_TYPE_HEADER: token_type,
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


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Snowflake: a snowflake_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("token") or "").strip()
    if not token:
        msg = "Snowflake: credential has an empty 'token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    token_type = str(payload.get("token_type") or "").strip().upper()
    if token_type not in _VALID_TOKEN_TYPES:
        msg = (
            "Snowflake: credential 'token_type' must be 'KEYPAIR_JWT' or "
            "'OAUTH'"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    account = str(payload.get("account") or "").strip()
    if not account:
        msg = "Snowflake: credential has an empty 'account'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token, token_type, account


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_EXECUTE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Snowflake: unsupported operation {operation!r}"
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
        logger.error("snowflake.request_failed", operation=operation, error=str(exc))
        msg = f"Snowflake: network error on {operation}: {exc}"
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
            "snowflake.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Snowflake {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("snowflake.ok", operation=operation, status=response.status_code)
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
        code = payload.get("code")
        message = payload.get("message")
        if isinstance(code, str) and isinstance(message, str):
            return f"{code}: {message}"
        sql_state = payload.get("sqlState")
        if isinstance(message, str) and isinstance(sql_state, str):
            return f"SQLSTATE {sql_state}: {message}"
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
