"""QuickBooks Online node — query + invoice/customer CRUD via the v3 API.

Dispatches to the QuickBooks v3 REST API on the environment-specific
host (``sandbox-quickbooks.api.intuit.com`` vs
``quickbooks.api.intuit.com``) with the distinctive **realmId in the
URL path** — every call goes to ``/v3/company/{realmId}/...``. The
realmId is owned by the credential
(:class:`~weftlyflow.credentials.types.quickbooks_oauth2.QuickBooksOAuth2Credential`)
and the node prefixes it onto every operation path.

Parameters (all expression-capable):

* ``operation`` — ``query``, ``get_invoice``, ``create_invoice``,
  ``get_customer``, ``create_customer``.
* ``query`` — SQL-ish select (e.g. ``SELECT * FROM Customer``).
* ``invoice_id`` / ``customer_id`` — target resources.
* ``document`` — invoice / customer payload.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.quickbooks_oauth2 import host_from
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
from weftlyflow.nodes.integrations.quickbooks.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_CUSTOMER,
    OP_CREATE_INVOICE,
    OP_GET_CUSTOMER,
    OP_GET_INVOICE,
    OP_QUERY,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.quickbooks.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "quickbooks_oauth2"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.quickbooks_oauth2",)
_INVOICE_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_INVOICE, OP_CREATE_INVOICE},
)
_CUSTOMER_OPERATIONS: frozenset[str] = frozenset(
    {OP_GET_CUSTOMER, OP_CREATE_CUSTOMER},
)
_DOCUMENT_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_INVOICE, OP_CREATE_CUSTOMER},
)

log = structlog.get_logger(__name__)


class QuickBooksNode(BaseNode):
    """Dispatch a single QuickBooks v3 call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.quickbooks",
        version=1,
        display_name="QuickBooks Online",
        description="Query SQL and CRUD invoices/customers via the QBO v3 API.",
        icon="icons/quickbooks.svg",
        category=NodeCategory.INTEGRATION,
        group=["accounting", "finance"],
        documentation_url=(
            "https://developer.intuit.com/app/developer/qbo/docs/api/accounting"
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
                default=OP_QUERY,
                required=True,
                options=[
                    PropertyOption(value=OP_QUERY, label="Query"),
                    PropertyOption(value=OP_GET_INVOICE, label="Get Invoice"),
                    PropertyOption(value=OP_CREATE_INVOICE, label="Create Invoice"),
                    PropertyOption(value=OP_GET_CUSTOMER, label="Get Customer"),
                    PropertyOption(value=OP_CREATE_CUSTOMER, label="Create Customer"),
                ],
            ),
            PropertySchema(
                name="query",
                display_name="Query",
                type="string",
                description="QuickBooks SQL (e.g. SELECT * FROM Customer).",
                display_options=DisplayOptions(show={"operation": [OP_QUERY]}),
            ),
            PropertySchema(
                name="invoice_id",
                display_name="Invoice ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_INVOICE_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="customer_id",
                display_name="Customer ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_CUSTOMER_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="document",
                display_name="Document",
                type="json",
                description="Invoice/customer body — naked JSON, no wrapper.",
                display_options=DisplayOptions(
                    show={"operation": list(_DOCUMENT_OPERATIONS)},
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one QuickBooks v3 call per input item."""
        token, realm_id, host, minor_version = await _resolve_credentials(ctx)
        base_url = f"https://{host}/v3/company/{realm_id}"
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        headers = {
            "Authorization": f"Bearer {token}",
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
                        minor_version=minor_version,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[str, str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "QuickBooks: a quickbooks_oauth2 credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "QuickBooks: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    realm_id = str(payload.get("realm_id") or "").strip()
    if not realm_id:
        msg = "QuickBooks: credential has an empty 'realm_id'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    environment = str(payload.get("environment") or "production").strip()
    try:
        host = host_from(environment)
    except ValueError as exc:
        raise NodeExecutionError(
            str(exc), node_id=ctx.node.id, original=exc,
        ) from exc
    minor_version = str(payload.get("minor_version") or "").strip()
    return token, realm_id, host, minor_version


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    minor_version: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_QUERY).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"QuickBooks: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    final_query: dict[str, Any] = dict(query)
    if minor_version:
        final_query.setdefault("minorversion", minor_version)
    request_headers = dict(headers)
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    try:
        response = await client.request(
            method,
            path,
            params=final_query or None,
            json=body,
            headers=request_headers,
        )
    except httpx.HTTPError as exc:
        logger.error("quickbooks.request_failed", operation=operation, error=str(exc))
        msg = f"QuickBooks: network error on {operation}: {exc}"
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
            "quickbooks.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"QuickBooks {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("quickbooks.ok", operation=operation, status=response.status_code)
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
        fault = payload.get("Fault")
        if isinstance(fault, dict):
            errors = fault.get("Error")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    detail = first.get("Detail") or first.get("Message")
                    if isinstance(detail, str) and detail:
                        return detail
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
