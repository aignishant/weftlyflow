"""Unit tests for :class:`ShopifyNode`.

Exercises every supported operation against a respx-mocked Shopify Admin
REST API. Verifies the ``X-Shopify-Access-Token`` header, the per-shop
base URL composed from ``<shop>.myshopify.com``, and convenience
``products`` / ``orders`` keys on list operations.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ShopifyAdminCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.shopify import ShopifyNode
from weftlyflow.nodes.integrations.shopify.operations import build_request

_CRED_ID: str = "cr_shop"
_PROJECT_ID: str = "pr_test"
_SHOP: str = "my-store"
_VERSION: str = "2024-07"
_BASE: str = f"https://{_SHOP}.myshopify.com/admin/api/{_VERSION}"


def _resolver(
    *,
    shop: str = _SHOP,
    access_token: str = "shpat_abc",
    api_version: str = _VERSION,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.shopify_admin": ShopifyAdminCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.shopify_admin",
                {"shop": shop, "access_token": access_token, "api_version": api_version},
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(
    node: Node,
    *,
    inputs: list[Item] | None = None,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": list(inputs or [])},
        credential_resolver=resolver,
    )


# --- list_products -------------------------------------------------------


@respx.mock
async def test_list_products_uses_access_token_header_and_convenience_key() -> None:
    route = respx.get(f"{_BASE}/products.json").mock(
        return_value=Response(
            200, json={"products": [{"id": 1}, {"id": 2}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={"operation": "list_products", "limit": 25, "vendor": "Acme"},
        credentials={"shopify_admin": _CRED_ID},
    )
    out = await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [p["id"] for p in result.json["products"]] == [1, 2]
    request = route.calls.last.request
    assert request.headers["x-shopify-access-token"] == "shpat_abc"
    assert "authorization" not in request.headers
    query = dict(request.url.params)
    assert query == {"limit": "25", "vendor": "Acme"}


@respx.mock
async def test_list_products_caps_limit_at_250() -> None:
    route = respx.get(f"{_BASE}/products.json").mock(
        return_value=Response(200, json={"products": []}),
    )
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={"operation": "list_products", "limit": 9999},
        credentials={"shopify_admin": _CRED_ID},
    )
    await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert dict(route.calls.last.request.url.params)["limit"] == "250"


# --- get / create / update product ---------------------------------------


@respx.mock
async def test_get_product_includes_version_in_path() -> None:
    route = respx.get(f"{_BASE}/products/42.json").mock(
        return_value=Response(200, json={"product": {"id": 42}}),
    )
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={"operation": "get_product", "product_id": "42"},
        credentials={"shopify_admin": _CRED_ID},
    )
    await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


@respx.mock
async def test_create_product_wraps_body_in_product_envelope() -> None:
    route = respx.post(f"{_BASE}/products.json").mock(
        return_value=Response(201, json={"product": {"id": 99}}),
    )
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={
            "operation": "create_product",
            "product": {"title": "Coffee Beans", "vendor": "Acme"},
        },
        credentials={"shopify_admin": _CRED_ID},
    )
    await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"product": {"title": "Coffee Beans", "vendor": "Acme"}}


@respx.mock
async def test_update_product_injects_id_into_product_body() -> None:
    route = respx.put(f"{_BASE}/products/42.json").mock(
        return_value=Response(200, json={"product": {"id": 42}}),
    )
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={
            "operation": "update_product",
            "product_id": "42",
            "product": {"title": "Renamed"},
        },
        credentials={"shopify_admin": _CRED_ID},
    )
    await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"product": {"title": "Renamed", "id": 42}}


# --- list_orders / get_order --------------------------------------------


@respx.mock
async def test_list_orders_forwards_status_and_surfaces_orders_key() -> None:
    route = respx.get(f"{_BASE}/orders.json").mock(
        return_value=Response(200, json={"orders": [{"id": 1}]}),
    )
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={"operation": "list_orders", "status": "any", "limit": 10},
        credentials={"shopify_admin": _CRED_ID},
    )
    out = await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [o["id"] for o in result.json["orders"]] == [1]
    query = dict(route.calls.last.request.url.params)
    assert query == {"limit": "10", "status": "any"}


@respx.mock
async def test_list_orders_rejects_invalid_status() -> None:
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={"operation": "list_orders", "status": "bogus"},
        credentials={"shopify_admin": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid order status"):
        await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_get_order_hits_order_path() -> None:
    route = respx.get(f"{_BASE}/orders/7.json").mock(
        return_value=Response(200, json={"order": {"id": 7}}),
    )
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={"operation": "get_order", "order_id": "7"},
        credentials={"shopify_admin": _CRED_ID},
    )
    await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- error & credential paths -------------------------------------------


@respx.mock
async def test_api_error_surfaces_errors_dict() -> None:
    respx.post(f"{_BASE}/products.json").mock(
        return_value=Response(
            422, json={"errors": {"title": ["can't be blank"]}},
        ),
    )
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={
            "operation": "create_product",
            "product": {"title": "temp"},
        },
        credentials={"shopify_admin": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="title"):
        await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={"operation": "get_product", "product_id": "1"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await ShopifyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_credential_fields_raise() -> None:
    node = Node(
        id="node_1",
        name="Shopify",
        type="weftlyflow.shopify",
        parameters={"operation": "get_product", "product_id": "1"},
        credentials={"shopify_admin": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'shop' and 'access_token'"):
        await ShopifyNode().execute(
            _ctx_for(node, resolver=_resolver(access_token="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_create_requires_title_on_product() -> None:
    with pytest.raises(ValueError, match=r"product\.title is required"):
        build_request("create_product", {"product": {"vendor": "Acme"}})


def test_build_request_update_requires_product_id() -> None:
    with pytest.raises(ValueError, match="'product_id' is required"):
        build_request("update_product", {"product": {"title": "x"}})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_product", {})
