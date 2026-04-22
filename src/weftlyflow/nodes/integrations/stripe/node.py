"""Stripe node — customers and payment intents.

Dispatches to Stripe's REST API at ``https://api.stripe.com``. Every
request carries ``Authorization: Bearer <sk_live_... | sk_test_...>`` from
a :class:`~weftlyflow.credentials.types.bearer_token.BearerTokenCredential`
(the ``token`` field holds the secret key).

The node forwards an ``Idempotency-Key`` header when the node parameter
``idempotency_key`` is set — Stripe guarantees at-most-once processing
across retries when this key is reused. See
https://stripe.com/docs/api/idempotent_requests.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` object.
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
from weftlyflow.nodes.integrations.stripe.constants import (
    API_BASE_URL,
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_CUSTOMER,
    OP_CREATE_PAYMENT_INTENT,
    OP_LIST_CUSTOMERS,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.stripe.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "stripe_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.bearer_token",)

log = structlog.get_logger(__name__)


class StripeNode(BaseNode):
    """Dispatch a single Stripe REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.stripe",
        version=1,
        display_name="Stripe",
        description="Create customers, list customers, create payment intents.",
        icon="icons/stripe.svg",
        category=NodeCategory.INTEGRATION,
        group=["payments", "e-commerce"],
        documentation_url="https://stripe.com/docs/api",
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
                default=OP_CREATE_CUSTOMER,
                required=True,
                options=[
                    PropertyOption(value=OP_CREATE_CUSTOMER, label="Create Customer"),
                    PropertyOption(value=OP_LIST_CUSTOMERS, label="List Customers"),
                    PropertyOption(
                        value=OP_CREATE_PAYMENT_INTENT,
                        label="Create Payment Intent",
                    ),
                ],
            ),
            PropertySchema(
                name="email",
                display_name="Email",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_CUSTOMER, OP_LIST_CUSTOMERS]},
                ),
            ),
            PropertySchema(
                name="name",
                display_name="Name",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_CREATE_CUSTOMER]}),
            ),
            PropertySchema(
                name="description",
                display_name="Description",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_CREATE_CUSTOMER, OP_CREATE_PAYMENT_INTENT],
                    },
                ),
            ),
            PropertySchema(
                name="metadata",
                display_name="Metadata",
                type="json",
                description="Flat object of metadata key/value pairs.",
                display_options=DisplayOptions(
                    show={
                        "operation": [OP_CREATE_CUSTOMER, OP_CREATE_PAYMENT_INTENT],
                    },
                ),
            ),
            PropertySchema(
                name="amount",
                display_name="Amount (in smallest currency unit)",
                type="number",
                description="E.g. 2000 = $20.00 USD.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PAYMENT_INTENT]},
                ),
            ),
            PropertySchema(
                name="currency",
                display_name="Currency",
                type="string",
                default="usd",
                description="3-letter ISO 4217 code (lowercase).",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PAYMENT_INTENT]},
                ),
            ),
            PropertySchema(
                name="customer",
                display_name="Customer ID",
                type="string",
                description="Attach the PaymentIntent to an existing Stripe customer.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PAYMENT_INTENT]},
                ),
            ),
            PropertySchema(
                name="payment_method_types",
                display_name="Payment Method Types",
                type="string",
                default="card",
                description="Comma-separated list, e.g. 'card,us_bank_account'.",
                display_options=DisplayOptions(
                    show={"operation": [OP_CREATE_PAYMENT_INTENT]},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                default=DEFAULT_LIST_LIMIT,
                display_options=DisplayOptions(show={"operation": [OP_LIST_CUSTOMERS]}),
            ),
            PropertySchema(
                name="starting_after",
                display_name="Starting After",
                type="string",
                description="Cursor for pagination (customer id).",
                display_options=DisplayOptions(show={"operation": [OP_LIST_CUSTOMERS]}),
            ),
            PropertySchema(
                name="idempotency_key",
                display_name="Idempotency Key",
                type="string",
                description="Optional Idempotency-Key header.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Stripe REST call per input item."""
        secret_key = await _resolve_secret_key(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, secret_key=secret_key, logger=bound,
                    ),
                )
        return [results]


async def _resolve_secret_key(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Stripe: a bearer-token credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    key = str(payload.get("token") or "").strip()
    if not key:
        msg = "Stripe: credential has an empty 'token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return key


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    secret_key: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_CREATE_CUSTOMER).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Stripe: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, form, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc

    headers: dict[str, str] = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    idempotency_key = str(params.get("idempotency_key") or "").strip()
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            data=form or None,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.error("stripe.request_failed", operation=operation, error=str(exc))
        msg = f"Stripe: network error on {operation}: {exc}"
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
            "stripe.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Stripe {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("stripe.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
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
    return f"HTTP {status_code}"
