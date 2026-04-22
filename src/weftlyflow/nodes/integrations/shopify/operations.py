"""Per-operation request builders for the Shopify Admin REST API node.

Each builder returns ``(http_method, relative_path, json_body, query_params)``.
Paths are relative to ``/admin/api/{version}/`` — the node layer prepends
that prefix so the version lives with the credential/operation config
rather than the builder.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.shopify.constants import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    OP_CREATE_PRODUCT,
    OP_GET_ORDER,
    OP_GET_PRODUCT,
    OP_LIST_ORDERS,
    OP_LIST_PRODUCTS,
    OP_UPDATE_PRODUCT,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_ORDER_STATUS_VALUES: frozenset[str] = frozenset({"open", "closed", "cancelled", "any"})


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Shopify: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_products(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_limit(params.get("limit"))}
    since_id = str(params.get("since_id") or "").strip()
    if since_id:
        query["since_id"] = since_id
    vendor = str(params.get("vendor") or "").strip()
    if vendor:
        query["vendor"] = vendor
    return "GET", "products.json", None, query


def _build_get_product(params: dict[str, Any]) -> RequestSpec:
    product_id = _required(params, "product_id")
    path = f"products/{quote(product_id, safe='')}.json"
    return "GET", path, None, {}


def _build_create_product(params: dict[str, Any]) -> RequestSpec:
    product = _required_object(params, "product")
    title = str(product.get("title") or "").strip()
    if not title:
        msg = "Shopify: product.title is required"
        raise ValueError(msg)
    return "POST", "products.json", {"product": product}, {}


def _build_update_product(params: dict[str, Any]) -> RequestSpec:
    product_id = _required(params, "product_id")
    product = _required_object(params, "product")
    product = {**product, "id": int(product_id) if product_id.isdigit() else product_id}
    path = f"products/{quote(product_id, safe='')}.json"
    return "PUT", path, {"product": product}, {}


def _build_list_orders(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_limit(params.get("limit"))}
    status = str(params.get("status") or "").strip().lower()
    if status:
        if status not in _ORDER_STATUS_VALUES:
            msg = f"Shopify: invalid order status {status!r}"
            raise ValueError(msg)
        query["status"] = status
    since_id = str(params.get("since_id") or "").strip()
    if since_id:
        query["since_id"] = since_id
    return "GET", "orders.json", None, query


def _build_get_order(params: dict[str, Any]) -> RequestSpec:
    order_id = _required(params, "order_id")
    path = f"orders/{quote(order_id, safe='')}.json"
    return "GET", path, None, {}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Shopify: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_object(params: dict[str, Any], key: str) -> dict[str, Any]:
    value = params.get(key)
    if not isinstance(value, dict) or not value:
        msg = f"Shopify: {key!r} must be a non-empty JSON object"
        raise ValueError(msg)
    return value


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Shopify: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Shopify: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_LIST_LIMIT)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_PRODUCTS: _build_list_products,
    OP_GET_PRODUCT: _build_get_product,
    OP_CREATE_PRODUCT: _build_create_product,
    OP_UPDATE_PRODUCT: _build_update_product,
    OP_LIST_ORDERS: _build_list_orders,
    OP_GET_ORDER: _build_get_order,
}
