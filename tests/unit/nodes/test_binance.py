"""Unit tests for :class:`BinanceNode` and ``BinanceApiCredential``.

Binance Spot is the catalog's first integration that injects its
HMAC-SHA256 signature as a **query parameter**: signed endpoints
append ``signature=<hex>`` over the URL-encoded query string. The
tests verify that (a) the credential alone injects only the
``X-MBX-APIKEY`` header, (b) the module helper ``sign_query`` matches
a locally-computed reference, and (c) the node appends ``timestamp``
and ``signature`` to signed operations but leaves public endpoints
untouched.
"""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BinanceApiCredential
from weftlyflow.credentials.types.binance_api import host_for, sign_query
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.binance import BinanceNode
from weftlyflow.nodes.integrations.binance.operations import build_request, is_signed

_CRED_ID: str = "cr_binance"
_PROJECT_ID: str = "pr_test"
_KEY: str = "mbx_key_abc"
_SECRET: str = "mbx_secret_xyz"
_LIVE: str = "https://api.binance.com"
_TESTNET: str = "https://testnet.binance.vision"


def _resolver(
    *,
    api_key: str = _KEY,
    api_secret: str = _SECRET,
    environment: str = "live",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.binance_api": BinanceApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.binance_api",
                {
                    "api_key": api_key,
                    "api_secret": api_secret,
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


def _reference_hmac(query_string: str) -> str:
    return hmac.new(
        _SECRET.encode(), query_string.encode(), hashlib.sha256,
    ).hexdigest()


# --- credential: X-MBX-APIKEY only --------------------------------


async def test_credential_inject_sets_api_key_header_only() -> None:
    request = httpx.Request("GET", f"{_LIVE}/api/v3/account")
    out = await BinanceApiCredential().inject(
        {"api_key": _KEY, "api_secret": _SECRET}, request,
    )
    assert out.headers["X-MBX-APIKEY"] == _KEY
    # Inject must NOT sign — that's a node responsibility for signed ops.
    assert "signature" not in dict(out.url.params)


def test_sign_query_matches_reference() -> None:
    query = "symbol=BTCUSDT&side=BUY&type=LIMIT&timestamp=1700000000000"
    assert sign_query(api_secret=_SECRET, total_params=query) == _reference_hmac(query)


def test_host_for_routes_live_and_testnet() -> None:
    assert host_for("live") == _LIVE
    assert host_for("testnet") == _TESTNET
    assert host_for(None) == _LIVE
    assert host_for("unknown") == _LIVE


def test_is_signed_marks_trading_endpoints() -> None:
    assert is_signed("account_info")
    assert is_signed("place_order")
    assert is_signed("cancel_order")
    assert not is_signed("get_ticker_price")


# --- account_info -------------------------------------------------


@respx.mock
async def test_account_info_appends_timestamp_and_signature() -> None:
    route = respx.get(f"{_LIVE}/api/v3/account").mock(
        return_value=Response(200, json={"balances": []}),
    )
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={"operation": "account_info"},
        credentials={"binance_api": _CRED_ID},
    )
    await BinanceNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    qs = parse_qs(sent.url.query.decode() if isinstance(sent.url.query, bytes) else sent.url.query)
    assert "timestamp" in qs
    assert "signature" in qs
    assert sent.headers["X-MBX-APIKEY"] == _KEY
    # Signature must equal HMAC over the query string minus the signature itself.
    raw_query = sent.url.query.decode() if isinstance(sent.url.query, bytes) else sent.url.query
    signed_portion = raw_query.rsplit("&signature=", 1)[0]
    assert qs["signature"][0] == _reference_hmac(signed_portion)


@respx.mock
async def test_account_info_uses_testnet_host_when_env_testnet() -> None:
    route = respx.get(f"{_TESTNET}/api/v3/account").mock(
        return_value=Response(200, json={"balances": []}),
    )
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={"operation": "account_info"},
        credentials={"binance_api": _CRED_ID},
    )
    await BinanceNode().execute(
        _ctx_for(node, resolver=_resolver(environment="testnet")), [Item()],
    )
    assert route.called


# --- get_ticker_price ---------------------------------------------


@respx.mock
async def test_get_ticker_price_is_unsigned() -> None:
    route = respx.get(f"{_LIVE}/api/v3/ticker/price").mock(
        return_value=Response(200, json={"symbol": "BTCUSDT", "price": "50000.00"}),
    )
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={"operation": "get_ticker_price", "symbol": "BTCUSDT"},
        credentials={"binance_api": _CRED_ID},
    )
    await BinanceNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    qs = parse_qs(sent.url.query.decode() if isinstance(sent.url.query, bytes) else sent.url.query)
    assert qs.get("symbol") == ["BTCUSDT"]
    assert "signature" not in qs
    assert "timestamp" not in qs


# --- place_order --------------------------------------------------


@respx.mock
async def test_place_limit_order_carries_price_and_quantity() -> None:
    route = respx.post(f"{_LIVE}/api/v3/order").mock(
        return_value=Response(200, json={"orderId": 42}),
    )
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={
            "operation": "place_order",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "price": "45000.00",
            "quantity": "0.01",
            "time_in_force": "GTC",
        },
        credentials={"binance_api": _CRED_ID},
    )
    await BinanceNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    qs = parse_qs(sent.url.query.decode() if isinstance(sent.url.query, bytes) else sent.url.query)
    assert qs["symbol"] == ["BTCUSDT"]
    assert qs["side"] == ["BUY"]
    assert qs["type"] == ["LIMIT"]
    assert qs["price"] == ["45000.00"]
    assert qs["quantity"] == ["0.01"]
    assert qs["timeInForce"] == ["GTC"]
    assert "timestamp" in qs
    assert "signature" in qs


@respx.mock
async def test_place_market_order_accepts_quote_order_qty() -> None:
    route = respx.post(f"{_LIVE}/api/v3/order").mock(
        return_value=Response(200, json={"orderId": 43}),
    )
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={
            "operation": "place_order",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "quote_order_qty": "100.00",
        },
        credentials={"binance_api": _CRED_ID},
    )
    await BinanceNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    qs = parse_qs(sent.url.query.decode() if isinstance(sent.url.query, bytes) else sent.url.query)
    assert qs["type"] == ["MARKET"]
    assert qs["quoteOrderQty"] == ["100.00"]
    assert "price" not in qs


def test_place_limit_order_requires_price() -> None:
    with pytest.raises(ValueError, match="'price' is required"):
        build_request(
            "place_order",
            {
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "limit",
                "quantity": "0.01",
            },
        )


def test_place_market_order_requires_quantity_or_quote() -> None:
    with pytest.raises(ValueError, match="'quantity' or 'quote_order_qty'"):
        build_request(
            "place_order",
            {"symbol": "BTCUSDT", "side": "buy", "order_type": "market"},
        )


def test_place_order_rejects_unknown_side() -> None:
    with pytest.raises(ValueError, match="'side' must be"):
        build_request(
            "place_order",
            {
                "symbol": "BTCUSDT",
                "side": "maybe",
                "order_type": "market",
                "quantity": "1",
            },
        )


# --- cancel_order -------------------------------------------------


@respx.mock
async def test_cancel_order_uses_delete_with_order_id() -> None:
    route = respx.delete(f"{_LIVE}/api/v3/order").mock(
        return_value=Response(200, json={"orderId": 42}),
    )
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={"operation": "cancel_order", "symbol": "BTCUSDT", "order_id": "42"},
        credentials={"binance_api": _CRED_ID},
    )
    await BinanceNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    qs = parse_qs(sent.url.query.decode() if isinstance(sent.url.query, bytes) else sent.url.query)
    assert qs["orderId"] == ["42"]
    assert qs["symbol"] == ["BTCUSDT"]


def test_cancel_order_requires_identifier() -> None:
    with pytest.raises(ValueError, match="'order_id' or 'orig_client_order_id'"):
        build_request("cancel_order", {"symbol": "BTCUSDT"})


# --- errors -------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_msg_field() -> None:
    respx.get(f"{_LIVE}/api/v3/account").mock(
        return_value=Response(401, json={"code": -2014, "msg": "API-key format invalid."}),
    )
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={"operation": "account_info"},
        credentials={"binance_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="API-key format invalid"):
        await BinanceNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={"operation": "account_info"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await BinanceNode().execute(_ctx_for(node), [Item()])


async def test_empty_secret_raises() -> None:
    resolver = _resolver(api_secret="")
    node = Node(
        id="node_1",
        name="Binance",
        type="weftlyflow.binance",
        parameters={"operation": "account_info"},
        credentials={"binance_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_secret'"):
        await BinanceNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
