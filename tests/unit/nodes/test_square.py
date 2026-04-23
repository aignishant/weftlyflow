"""Unit tests for :class:`SquareNode`.

Exercises every supported operation against a respx-mocked Square v2
API. Verifies the mandatory ``Square-Version`` header, environment-
specific host routing, ``create_payment`` idempotency-key auto-gen and
``amount_money`` envelope, and ``search_orders`` POST-with-body listing.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import SquareApiCredential
from weftlyflow.credentials.types.square_api import host_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.square import SquareNode
from weftlyflow.nodes.integrations.square.operations import build_request

_CRED_ID: str = "cr_square"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "EAAA-square-token"
_VERSION: str = "2024-12-18"
_BASE: str = "https://connect.squareupsandbox.com"


def _resolver(
    *,
    token: str = _TOKEN,
    version: str = _VERSION,
    environment: str = "sandbox",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.square_api": SquareApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.square_api",
                {
                    "access_token": token,
                    "api_version": version,
                    "environment": environment,
                },
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(
    node: Node,
    *,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=resolver or _resolver(),
    )


# --- host_from -------------------------------------------------------


def test_host_from_sandbox_and_production() -> None:
    assert host_from("sandbox") == "connect.squareupsandbox.com"
    assert host_from("production") == "connect.squareup.com"


def test_host_from_rejects_unknown_environment() -> None:
    with pytest.raises(ValueError, match="'environment' must be one of"):
        host_from("staging")


# --- list_customers --------------------------------------------------


@respx.mock
async def test_list_customers_sends_version_header() -> None:
    route = respx.get(f"{_BASE}/v2/customers").mock(
        return_value=Response(200, json={"customers": []}),
    )
    node = Node(
        id="node_1",
        name="Square",
        type="weftlyflow.square",
        parameters={"operation": "list_customers", "limit": 50},
        credentials={"square_api": _CRED_ID},
    )
    await SquareNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.headers["Square-Version"] == _VERSION
    assert request.url.params.get("limit") == "50"


# --- get_customer ----------------------------------------------------


@respx.mock
async def test_get_customer_hits_resource_path() -> None:
    respx.get(f"{_BASE}/v2/customers/CUST-1").mock(
        return_value=Response(200, json={"customer": {"id": "CUST-1"}}),
    )
    node = Node(
        id="node_1",
        name="Square",
        type="weftlyflow.square",
        parameters={"operation": "get_customer", "customer_id": "CUST-1"},
        credentials={"square_api": _CRED_ID},
    )
    await SquareNode().execute(_ctx_for(node), [Item()])


def test_get_customer_requires_customer_id() -> None:
    with pytest.raises(ValueError, match="'customer_id' is required"):
        build_request("get_customer", {})


# --- create_payment --------------------------------------------------


@respx.mock
async def test_create_payment_wraps_amount_money_envelope() -> None:
    route = respx.post(f"{_BASE}/v2/payments").mock(
        return_value=Response(200, json={"payment": {"id": "PAY-1"}}),
    )
    node = Node(
        id="node_1",
        name="Square",
        type="weftlyflow.square",
        parameters={
            "operation": "create_payment",
            "source_id": "cnon:card-nonce-ok",
            "amount": 1099,
            "currency": "USD",
            "idempotency_key": "ik-fixed-1",
            "location_id": "L1",
        },
        credentials={"square_api": _CRED_ID},
    )
    await SquareNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "source_id": "cnon:card-nonce-ok",
        "idempotency_key": "ik-fixed-1",
        "amount_money": {"amount": 1099, "currency": "USD"},
        "location_id": "L1",
    }


def test_create_payment_auto_generates_idempotency_key() -> None:
    _, _, body, _ = build_request(
        "create_payment",
        {"source_id": "cnon:x", "amount": 100, "currency": "usd"},
    )
    assert body is not None
    assert isinstance(body["idempotency_key"], str)
    assert len(body["idempotency_key"]) >= 16
    assert body["amount_money"] == {"amount": 100, "currency": "USD"}


def test_create_payment_requires_source_id_and_amount() -> None:
    with pytest.raises(ValueError, match="'source_id' is required"):
        build_request("create_payment", {})
    with pytest.raises(ValueError, match="'amount' is required"):
        build_request("create_payment", {"source_id": "x"})


# --- search_orders ---------------------------------------------------


@respx.mock
async def test_search_orders_posts_with_body() -> None:
    route = respx.post(f"{_BASE}/v2/orders/search").mock(
        return_value=Response(200, json={"orders": []}),
    )
    node = Node(
        id="node_1",
        name="Square",
        type="weftlyflow.square",
        parameters={
            "operation": "search_orders",
            "location_ids": "L1, L2",
            "query": {"filter": {"state_filter": {"states": ["OPEN"]}}},
            "limit": 10,
        },
        credentials={"square_api": _CRED_ID},
    )
    await SquareNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["location_ids"] == ["L1", "L2"]
    assert body["query"] == {"filter": {"state_filter": {"states": ["OPEN"]}}}
    assert body["limit"] == 10


def test_search_orders_accepts_list_location_ids() -> None:
    _, _, body, _ = build_request(
        "search_orders",
        {"location_ids": ["A", " B "]},
    )
    assert body == {"location_ids": ["A", "B"]}


def test_search_orders_requires_location_ids() -> None:
    with pytest.raises(ValueError, match="'location_ids' is required"):
        build_request("search_orders", {})


# --- errors ----------------------------------------------------------


@respx.mock
async def test_errors_envelope_is_parsed() -> None:
    respx.get(f"{_BASE}/v2/customers/X").mock(
        return_value=Response(
            404,
            json={"errors": [{"detail": "Customer not found", "code": "NOT_FOUND"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Square",
        type="weftlyflow.square",
        parameters={"operation": "get_customer", "customer_id": "X"},
        credentials={"square_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Customer not found"):
        await SquareNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Square",
        type="weftlyflow.square",
        parameters={"operation": "list_customers"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await SquareNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
