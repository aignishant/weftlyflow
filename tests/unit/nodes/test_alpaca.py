"""Unit tests for :class:`AlpacaNode` and ``AlpacaApiCredential``.

Alpaca splits auth across two named headers and routes the base URL
through a per-credential ``environment`` field. The tests verify both
behaviours: the credential emits the header pair verbatim, and the
node flips between paper and live hosts based on the credential.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import AlpacaApiCredential
from weftlyflow.credentials.types.alpaca_api import host_for
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.alpaca import AlpacaNode
from weftlyflow.nodes.integrations.alpaca.operations import build_request

_CRED_ID: str = "cr_alpaca"
_PROJECT_ID: str = "pr_test"
_KEY_ID: str = "AKXXXXXXXXXXXXXXXXXX"
_SECRET: str = "alpaca_secret_abc123"
_PAPER: str = "https://paper-api.alpaca.markets"
_LIVE: str = "https://api.alpaca.markets"


def _resolver(
    *,
    api_key_id: str = _KEY_ID,
    api_secret_key: str = _SECRET,
    environment: str = "paper",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.alpaca_api": AlpacaApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.alpaca_api",
                {
                    "api_key_id": api_key_id,
                    "api_secret_key": api_secret_key,
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


# --- credential: dual header emission -----------------------------


async def test_credential_inject_sets_both_apca_headers() -> None:
    request = httpx.Request("GET", f"{_PAPER}/v2/account")
    out = await AlpacaApiCredential().inject(
        {"api_key_id": _KEY_ID, "api_secret_key": _SECRET}, request,
    )
    assert out.headers["APCA-API-KEY-ID"] == _KEY_ID
    assert out.headers["APCA-API-SECRET-KEY"] == _SECRET


def test_host_for_routes_paper_and_live() -> None:
    assert host_for("paper") == _PAPER
    assert host_for("live") == _LIVE
    assert host_for(None) == _PAPER
    assert host_for("unknown") == _PAPER


# --- get_account -------------------------------------------------


@respx.mock
async def test_get_account_uses_paper_host_by_default() -> None:
    route = respx.get(f"{_PAPER}/v2/account").mock(
        return_value=Response(200, json={"id": "acc_1", "status": "ACTIVE"}),
    )
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={"operation": "get_account"},
        credentials={"alpaca_api": _CRED_ID},
    )
    await AlpacaNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.headers["APCA-API-KEY-ID"] == _KEY_ID
    assert sent.headers["APCA-API-SECRET-KEY"] == _SECRET


@respx.mock
async def test_get_account_routes_to_live_when_env_live() -> None:
    route = respx.get(f"{_LIVE}/v2/account").mock(
        return_value=Response(200, json={"id": "acc_1"}),
    )
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={"operation": "get_account"},
        credentials={"alpaca_api": _CRED_ID},
    )
    await AlpacaNode().execute(
        _ctx_for(node, resolver=_resolver(environment="live")), [Item()],
    )
    assert route.called


# --- list_positions ----------------------------------------------


@respx.mock
async def test_list_positions_hits_positions_endpoint() -> None:
    route = respx.get(f"{_PAPER}/v2/positions").mock(
        return_value=Response(200, json=[{"symbol": "AAPL", "qty": "10"}]),
    )
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={"operation": "list_positions"},
        credentials={"alpaca_api": _CRED_ID},
    )
    await AlpacaNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- get_clock ---------------------------------------------------


@respx.mock
async def test_get_clock_returns_market_status() -> None:
    respx.get(f"{_PAPER}/v2/clock").mock(
        return_value=Response(200, json={"is_open": True}),
    )
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={"operation": "get_clock"},
        credentials={"alpaca_api": _CRED_ID},
    )
    result = await AlpacaNode().execute(_ctx_for(node), [Item()])
    assert result[0][0].json["response"]["is_open"] is True


# --- place_order -------------------------------------------------


@respx.mock
async def test_place_market_order_with_qty() -> None:
    route = respx.post(f"{_PAPER}/v2/orders").mock(
        return_value=Response(200, json={"id": "ord_1"}),
    )
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={
            "operation": "place_order",
            "symbol": "AAPL",
            "side": "buy",
            "order_type": "market",
            "qty": "10",
            "time_in_force": "day",
        },
        credentials={"alpaca_api": _CRED_ID},
    )
    await AlpacaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["symbol"] == "AAPL"
    assert body["side"] == "buy"
    assert body["type"] == "market"
    assert body["qty"] == "10"
    assert body["time_in_force"] == "day"
    assert "limit_price" not in body


@respx.mock
async def test_place_limit_order_carries_limit_price() -> None:
    route = respx.post(f"{_PAPER}/v2/orders").mock(
        return_value=Response(200, json={"id": "ord_2"}),
    )
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={
            "operation": "place_order",
            "symbol": "AAPL",
            "side": "buy",
            "order_type": "limit",
            "qty": "5",
            "limit_price": "150.00",
            "time_in_force": "gtc",
        },
        credentials={"alpaca_api": _CRED_ID},
    )
    await AlpacaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["type"] == "limit"
    assert body["limit_price"] == "150.00"
    assert body["time_in_force"] == "gtc"


@respx.mock
async def test_place_order_accepts_notional_instead_of_qty() -> None:
    route = respx.post(f"{_PAPER}/v2/orders").mock(
        return_value=Response(200, json={"id": "ord_3"}),
    )
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={
            "operation": "place_order",
            "symbol": "AAPL",
            "side": "buy",
            "order_type": "market",
            "notional": "1000.00",
        },
        credentials={"alpaca_api": _CRED_ID},
    )
    await AlpacaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["notional"] == "1000.00"
    assert "qty" not in body


def test_place_order_requires_qty_or_notional() -> None:
    with pytest.raises(ValueError, match="'qty' or 'notional'"):
        build_request(
            "place_order",
            {"symbol": "AAPL", "side": "buy", "order_type": "market"},
        )


def test_place_limit_order_requires_limit_price() -> None:
    with pytest.raises(ValueError, match="'limit_price' is required"):
        build_request(
            "place_order",
            {
                "symbol": "AAPL",
                "side": "buy",
                "order_type": "limit",
                "qty": "5",
            },
        )


def test_place_order_rejects_unknown_side() -> None:
    with pytest.raises(ValueError, match="'side' must be"):
        build_request(
            "place_order",
            {"symbol": "AAPL", "side": "maybe", "order_type": "market", "qty": "1"},
        )


def test_place_order_rejects_unknown_time_in_force() -> None:
    with pytest.raises(ValueError, match="'time_in_force' must be"):
        build_request(
            "place_order",
            {
                "symbol": "AAPL",
                "side": "buy",
                "order_type": "market",
                "qty": "1",
                "time_in_force": "forever",
            },
        )


# --- errors ------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_message() -> None:
    respx.get(f"{_PAPER}/v2/account").mock(
        return_value=Response(403, json={"message": "forbidden"}),
    )
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={"operation": "get_account"},
        credentials={"alpaca_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="forbidden"):
        await AlpacaNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={"operation": "get_account"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AlpacaNode().execute(_ctx_for(node), [Item()])


async def test_empty_secret_raises() -> None:
    resolver = _resolver(api_secret_key="")
    node = Node(
        id="node_1",
        name="Alpaca",
        type="weftlyflow.alpaca",
        parameters={"operation": "get_account"},
        credentials={"alpaca_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_secret_key'"):
        await AlpacaNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
