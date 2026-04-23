"""NetSuite node — SuiteQL + record CRUD via OAuth 1.0a signed REST calls.

Dispatches to the SuiteTalk REST API on the account-specific host
(``<account>.suitetalk.api.netsuite.com``) with the distinctive
**OAuth 1.0a HMAC-SHA256** Authorization header — an algorithm absent
from the rest of the catalog. Every request is re-signed because the
nonce + timestamp change per call. Signing is delegated to
:func:`weftlyflow.credentials.types.netsuite_api.sign_request`.

Parameters (all expression-capable):

* ``operation`` — ``suiteql_query``, ``record_get``, ``record_create``,
  ``record_delete``.
* ``query`` / ``limit`` / ``offset`` — SuiteQL.
* ``record_type`` — record endpoint (e.g. ``customer``, ``invoice``).
* ``record_id`` — record target (get/delete).
* ``document`` — record body (create).

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.netsuite_api import account_host, sign_request
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
from weftlyflow.nodes.integrations.netsuite.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_RECORD_CREATE,
    OP_RECORD_DELETE,
    OP_RECORD_GET,
    OP_SUITEQL_QUERY,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.netsuite.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "netsuite_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.netsuite_api",)
_RECORD_TYPE_OPERATIONS: frozenset[str] = frozenset(
    {OP_RECORD_GET, OP_RECORD_CREATE, OP_RECORD_DELETE},
)
_RECORD_ID_OPERATIONS: frozenset[str] = frozenset(
    {OP_RECORD_GET, OP_RECORD_DELETE},
)

log = structlog.get_logger(__name__)


class NetSuiteNode(BaseNode):
    """Dispatch a single OAuth 1.0a-signed NetSuite call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.netsuite",
        version=1,
        display_name="NetSuite",
        description="Query SuiteQL and CRUD records via the SuiteTalk REST API.",
        icon="icons/netsuite.svg",
        category=NodeCategory.INTEGRATION,
        group=["erp", "finance"],
        documentation_url=(
            "https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/"
            "section_1559132836.html"
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
                default=OP_SUITEQL_QUERY,
                required=True,
                options=[
                    PropertyOption(value=OP_SUITEQL_QUERY, label="SuiteQL Query"),
                    PropertyOption(value=OP_RECORD_GET, label="Get Record"),
                    PropertyOption(value=OP_RECORD_CREATE, label="Create Record"),
                    PropertyOption(value=OP_RECORD_DELETE, label="Delete Record"),
                ],
            ),
            PropertySchema(
                name="query",
                display_name="SuiteQL",
                type="string",
                description="e.g. SELECT id, email FROM customer WHERE ...",
                display_options=DisplayOptions(
                    show={"operation": [OP_SUITEQL_QUERY]},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_SUITEQL_QUERY]},
                ),
            ),
            PropertySchema(
                name="offset",
                display_name="Offset",
                type="number",
                display_options=DisplayOptions(
                    show={"operation": [OP_SUITEQL_QUERY]},
                ),
            ),
            PropertySchema(
                name="record_type",
                display_name="Record Type",
                type="string",
                description="e.g. customer, invoice, salesOrder.",
                display_options=DisplayOptions(
                    show={"operation": list(_RECORD_TYPE_OPERATIONS)},
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
                display_name="Record Document",
                type="json",
                description="Record body for create.",
                display_options=DisplayOptions(
                    show={"operation": [OP_RECORD_CREATE]},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one signed SuiteTalk REST call per input item."""
        oauth = await _resolve_credentials(ctx)
        try:
            host = account_host(oauth["account_id"])
        except ValueError as exc:
            raise NodeExecutionError(
                str(exc), node_id=ctx.node.id, original=exc,
            ) from exc
        base_url = f"https://{host}"
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
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
                        base_url=base_url,
                        oauth=oauth,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> dict[str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "NetSuite: a netsuite_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    fields = (
        "account_id",
        "consumer_key",
        "consumer_secret",
        "token_id",
        "token_secret",
    )
    resolved: dict[str, str] = {}
    for field in fields:
        value = str(payload.get(field) or "").strip()
        if not value:
            msg = f"NetSuite: credential has an empty {field!r}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        resolved[field] = value
    return resolved


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    base_url: str,
    oauth: dict[str, str],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_SUITEQL_QUERY).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"NetSuite: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query, extra_headers = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    full_url = f"{base_url}{path}"
    try:
        authorization = sign_request(
            method=method,
            url=full_url,
            query=query,
            account_id=oauth["account_id"],
            consumer_key=oauth["consumer_key"],
            consumer_secret=oauth["consumer_secret"],
            token_id=oauth["token_id"],
            token_secret=oauth["token_secret"],
        )
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request_headers: dict[str, str] = {
        "Authorization": authorization,
        "Accept": "application/json",
        **extra_headers,
    }
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
        logger.error("netsuite.request_failed", operation=operation, error=str(exc))
        msg = f"NetSuite: network error on {operation}: {exc}"
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
            "netsuite.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"NetSuite {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("netsuite.ok", operation=operation, status=response.status_code)
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
        details = payload.get("o:errorDetails")
        if isinstance(details, list) and details:
            first = details[0]
            if isinstance(first, dict):
                detail = first.get("detail")
                if isinstance(detail, str) and detail:
                    return detail
        title = payload.get("title")
        if isinstance(title, str) and title:
            return title
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
