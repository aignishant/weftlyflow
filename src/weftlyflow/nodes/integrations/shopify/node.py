"""Shopify node — Admin REST API for products and orders.

Dispatches to ``https://<shop>.myshopify.com/admin/api/<version>/...``
with ``X-Shopify-Access-Token: shpat_...`` from a
:class:`~weftlyflow.credentials.types.shopify_admin.ShopifyAdminCredential`.
The shop subdomain and API version live on the credential, so workflows
are portable between stores.

Parameters (all expression-capable):

* ``operation`` — ``list_products``, ``get_product``, ``create_product``,
  ``update_product``, ``list_orders``, ``get_order``.
* ``product_id`` — for get/update product.
* ``order_id`` — for get order.
* ``product`` — JSON object for create/update (must include ``title``
  on create).
* ``limit`` — list page size (capped at 250).
* ``since_id`` — pagination cursor for list operations.
* ``vendor`` — filter for ``list_products``.
* ``status`` — ``open`` / ``closed`` / ``cancelled`` / ``any`` for
  ``list_orders``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response``; list operations also surface a convenience
``products`` or ``orders`` list.
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
from weftlyflow.nodes.integrations.shopify.constants import (
    DEFAULT_API_VERSION,
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    OP_CREATE_PRODUCT,
    OP_GET_ORDER,
    OP_GET_PRODUCT,
    OP_LIST_ORDERS,
    OP_LIST_PRODUCTS,
    OP_UPDATE_PRODUCT,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.shopify.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "shopify_admin"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.shopify_admin",)
_PRODUCT_ID_OPERATIONS: frozenset[str] = frozenset({OP_GET_PRODUCT, OP_UPDATE_PRODUCT})
_PRODUCT_BODY_OPERATIONS: frozenset[str] = frozenset(
    {OP_CREATE_PRODUCT, OP_UPDATE_PRODUCT},
)
_LIST_OPERATIONS: frozenset[str] = frozenset({OP_LIST_PRODUCTS, OP_LIST_ORDERS})

log = structlog.get_logger(__name__)


class ShopifyNode(BaseNode):
    """Dispatch a single Shopify Admin REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.shopify",
        version=1,
        display_name="Shopify",
        description="Manage Shopify products and orders via the Admin REST API.",
        icon="icons/shopify.svg",
        category=NodeCategory.INTEGRATION,
        group=["e-commerce"],
        documentation_url="https://shopify.dev/docs/api/admin-rest",
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
                default=OP_LIST_PRODUCTS,
                required=True,
                options=[
                    PropertyOption(value=OP_LIST_PRODUCTS, label="List Products"),
                    PropertyOption(value=OP_GET_PRODUCT, label="Get Product"),
                    PropertyOption(value=OP_CREATE_PRODUCT, label="Create Product"),
                    PropertyOption(value=OP_UPDATE_PRODUCT, label="Update Product"),
                    PropertyOption(value=OP_LIST_ORDERS, label="List Orders"),
                    PropertyOption(value=OP_GET_ORDER, label="Get Order"),
                ],
            ),
            PropertySchema(
                name="product_id",
                display_name="Product ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_PRODUCT_ID_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="order_id",
                display_name="Order ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_GET_ORDER]}),
            ),
            PropertySchema(
                name="product",
                display_name="Product",
                type="json",
                description="Shopify product object (include 'title' on create).",
                display_options=DisplayOptions(
                    show={"operation": list(_PRODUCT_BODY_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                default=DEFAULT_LIST_LIMIT,
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="since_id",
                display_name="Since ID",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": list(_LIST_OPERATIONS)},
                ),
            ),
            PropertySchema(
                name="vendor",
                display_name="Vendor",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_PRODUCTS]}),
            ),
            PropertySchema(
                name="status",
                display_name="Status",
                type="options",
                default="",
                options=[
                    PropertyOption(value="", label="(default)"),
                    PropertyOption(value="open", label="Open"),
                    PropertyOption(value="closed", label="Closed"),
                    PropertyOption(value="cancelled", label="Cancelled"),
                    PropertyOption(value="any", label="Any"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_LIST_ORDERS]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Shopify Admin REST call per input item."""
        shop, token, version = await _resolve_credentials(ctx)
        base_url = f"https://{shop}.myshopify.com"
        api_prefix = f"/admin/api/{version}/"
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
                        token=token,
                        api_prefix=api_prefix,
                        logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Shopify: a shopify_admin credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    shop = str(payload.get("shop") or "").strip()
    token = str(payload.get("access_token") or "").strip()
    version = str(payload.get("api_version") or DEFAULT_API_VERSION).strip() or DEFAULT_API_VERSION
    if not shop or not token:
        msg = "Shopify: credential must have 'shop' and 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return shop, token, version


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    api_prefix: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_LIST_PRODUCTS).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Shopify: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, relative_path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    path = api_prefix + relative_path
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers={
                "X-Shopify-Access-Token": token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("shopify.request_failed", operation=operation, error=str(exc))
        msg = f"Shopify: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if operation == OP_LIST_PRODUCTS and isinstance(payload, dict):
        items_list = payload.get("products", [])
        result["products"] = items_list if isinstance(items_list, list) else []
    elif operation == OP_LIST_ORDERS and isinstance(payload, dict):
        items_list = payload.get("orders", [])
        result["orders"] = items_list if isinstance(items_list, list) else []
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "shopify.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Shopify {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("shopify.ok", operation=operation, status=response.status_code)
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
        errors = payload.get("errors")
        if isinstance(errors, str) and errors:
            return errors
        if isinstance(errors, dict) and errors:
            return "; ".join(f"{k}: {v}" for k, v in errors.items())
        if isinstance(errors, list) and errors:
            return "; ".join(str(e) for e in errors)
    return f"HTTP {status_code}"
