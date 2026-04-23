"""Plaid node — link token, item/accounts, transactions sync.

Dispatches against one of the three Plaid hosts (sandbox /
development / production) selected by the ``environment`` field on
the credential. Every request body carries **both** ``client_id`` and
``secret`` alongside the operation-specific fields — the node folds
these credentials in so :class:`PlaidApiCredential.inject` stays a
no-op and operation builders remain credential-free.

Parameters (all expression-capable):

* ``operation`` — ``link_token_create`` / ``item_get`` /
  ``accounts_get`` / ``transactions_sync``.
* ``client_name`` / ``client_user_id`` / ``products`` /
  ``country_codes`` / ``language`` / ``webhook`` — link_token_create.
* ``access_token`` — required for item/accounts/transactions.
* ``account_ids`` — optional filter on accounts_get.
* ``cursor`` / ``count`` — incremental paging on transactions_sync.

Output: one item per input item with ``operation``, ``status``, and
parsed ``response``.
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
from weftlyflow.nodes.integrations.plaid.constants import (
    DEFAULT_ENVIRONMENT,
    DEFAULT_TIMEOUT_SECONDS,
    HOSTS,
    OP_ACCOUNTS_GET,
    OP_ITEM_GET,
    OP_LINK_TOKEN_CREATE,
    OP_TRANSACTIONS_SYNC,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.plaid.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "plaid_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.plaid_api",)

log = structlog.get_logger(__name__)


class PlaidNode(BaseNode):
    """Dispatch a single Plaid API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.plaid",
        version=1,
        display_name="Plaid",
        description="Create link tokens, read items/accounts, and sync transactions via Plaid.",
        icon="icons/plaid.svg",
        category=NodeCategory.INTEGRATION,
        group=["finance"],
        documentation_url="https://plaid.com/docs/api/",
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
                default=OP_LINK_TOKEN_CREATE,
                required=True,
                options=[
                    PropertyOption(value=OP_LINK_TOKEN_CREATE, label="Create Link Token"),
                    PropertyOption(value=OP_ITEM_GET, label="Get Item"),
                    PropertyOption(value=OP_ACCOUNTS_GET, label="Get Accounts"),
                    PropertyOption(value=OP_TRANSACTIONS_SYNC, label="Sync Transactions"),
                ],
            ),
            PropertySchema(
                name="client_name",
                display_name="Client Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LINK_TOKEN_CREATE]}),
            ),
            PropertySchema(
                name="client_user_id",
                display_name="Client User ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LINK_TOKEN_CREATE]}),
            ),
            PropertySchema(
                name="products",
                display_name="Products",
                type="json",
                description="List of Plaid products, e.g. [\"auth\", \"transactions\"].",
                display_options=DisplayOptions(show={"operation": [OP_LINK_TOKEN_CREATE]}),
            ),
            PropertySchema(
                name="country_codes",
                display_name="Country Codes",
                type="json",
                description="List of two-letter country codes, e.g. [\"US\"].",
                display_options=DisplayOptions(show={"operation": [OP_LINK_TOKEN_CREATE]}),
            ),
            PropertySchema(
                name="language",
                display_name="Language",
                type="string",
                default="en",
                display_options=DisplayOptions(show={"operation": [OP_LINK_TOKEN_CREATE]}),
            ),
            PropertySchema(
                name="webhook",
                display_name="Webhook URL",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LINK_TOKEN_CREATE]}),
            ),
            PropertySchema(
                name="access_token",
                display_name="Access Token",
                type="string",
                type_options={"password": True},
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_ITEM_GET, OP_ACCOUNTS_GET, OP_TRANSACTIONS_SYNC],
                    },
                ),
            ),
            PropertySchema(
                name="account_ids",
                display_name="Account IDs",
                type="json",
                display_options=DisplayOptions(show={"operation": [OP_ACCOUNTS_GET]}),
            ),
            PropertySchema(
                name="cursor",
                display_name="Cursor",
                type="string",
                description="Previous sync cursor — omit for initial sync.",
                display_options=DisplayOptions(show={"operation": [OP_TRANSACTIONS_SYNC]}),
            ),
            PropertySchema(
                name="count",
                display_name="Count",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_TRANSACTIONS_SYNC]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Plaid call per input item."""
        payload = await _resolve_credentials(ctx)
        env = str(payload.get("environment") or DEFAULT_ENVIRONMENT).strip()
        host = HOSTS.get(env, HOSTS[DEFAULT_ENVIRONMENT])
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=host, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> dict[str, Any]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Plaid: a plaid_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _injector, payload = credential
    client_id = str(payload.get("client_id") or "").strip()
    secret = str(payload.get("secret") or "").strip()
    if not client_id or not secret:
        msg = "Plaid: credential has an empty 'client_id' or 'secret'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LINK_TOKEN_CREATE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Plaid: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    body = _fold_credentials(body, creds)
    request = client.build_request(
        method, path, params=query or None, json=body,
        headers={"Accept": "application/json"},
    )
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("plaid.request_failed", operation=operation, error=str(exc))
        msg = f"Plaid: network error on {operation}: {exc}"
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
            "plaid.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Plaid {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("plaid.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _fold_credentials(body: dict[str, Any], creds: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(body)
    out["client_id"] = str(creds.get("client_id") or "").strip()
    out["secret"] = str(creds.get("secret") or "").strip()
    return out


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, dict):
        for key in ("error_message", "display_message", "error_code"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
