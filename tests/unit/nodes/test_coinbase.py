"""Unit tests for :class:`CoinbaseNode` and ``CoinbaseExchangeCredential``.

Coinbase Exchange is the catalog's first integration that signs every
request: ``CB-ACCESS-SIGN`` is ``base64(HMAC-SHA256(base64_decode(secret),
timestamp + method + path + body))``. Tests verify the four ``CB-ACCESS-*``
headers are emitted and that the signature for a known request matches
a locally-computed reference value.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import CoinbaseExchangeCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.coinbase import CoinbaseNode
from weftlyflow.nodes.integrations.coinbase.operations import build_request

_CRED_ID: str = "cr_coinbase"
_PROJECT_ID: str = "pr_test"
_KEY: str = "cb_key_abc"
# The secret is base64-encoded to match Coinbase's documented shape.
_SECRET: str = base64.b64encode(b"coinbase-hmac-secret").decode()
_PASSPHRASE: str = "Tr@d3rP@ss"
_API: str = "https://api.exchange.coinbase.com"


def _resolver(
    *,
    api_key: str = _KEY,
    api_secret: str = _SECRET,
    passphrase: str = _PASSPHRASE,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.coinbase_exchange": CoinbaseExchangeCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.coinbase_exchange",
                {
                    "api_key": api_key,
                    "api_secret": api_secret,
                    "passphrase": passphrase,
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


def _reference_signature(
    *, timestamp: str, method: str, path: str, body: str,
) -> str:
    key = base64.b64decode(_SECRET)
    message = f"{timestamp}{method}{path}{body}".encode()
    return base64.b64encode(
        hmac.new(key, message, hashlib.sha256).digest(),
    ).decode()


# --- credential: quad-header HMAC signing -------------------------


async def test_credential_inject_emits_four_cb_access_headers() -> None:
    request = httpx.Request("GET", f"{_API}/accounts")
    out = await CoinbaseExchangeCredential().inject(
        {"api_key": _KEY, "api_secret": _SECRET, "passphrase": _PASSPHRASE},
        request,
    )
    assert out.headers["CB-ACCESS-KEY"] == _KEY
    assert out.headers["CB-ACCESS-PASSPHRASE"] == _PASSPHRASE
    timestamp = out.headers["CB-ACCESS-TIMESTAMP"]
    assert timestamp.isdigit()
    # The signature must match a locally computed HMAC.
    expected = _reference_signature(
        timestamp=timestamp, method="GET", path="/accounts", body="",
    )
    assert out.headers["CB-ACCESS-SIGN"] == expected


async def test_credential_signature_includes_request_body() -> None:
    body = json.dumps({"product_id": "BTC-USD", "side": "buy", "type": "limit"})
    request = httpx.Request(
        "POST",
        f"{_API}/orders",
        content=body.encode(),
        headers={"Content-Type": "application/json"},
    )
    out = await CoinbaseExchangeCredential().inject(
        {"api_key": _KEY, "api_secret": _SECRET, "passphrase": _PASSPHRASE},
        request,
    )
    timestamp = out.headers["CB-ACCESS-TIMESTAMP"]
    expected = _reference_signature(
        timestamp=timestamp, method="POST", path="/orders", body=body,
    )
    assert out.headers["CB-ACCESS-SIGN"] == expected


async def test_credential_signature_includes_query_string() -> None:
    request = httpx.Request("GET", f"{_API}/orders?status=open&limit=10")
    out = await CoinbaseExchangeCredential().inject(
        {"api_key": _KEY, "api_secret": _SECRET, "passphrase": _PASSPHRASE},
        request,
    )
    timestamp = out.headers["CB-ACCESS-TIMESTAMP"]
    expected = _reference_signature(
        timestamp=timestamp,
        method="GET",
        path="/orders?status=open&limit=10",
        body="",
    )
    assert out.headers["CB-ACCESS-SIGN"] == expected


# --- list_accounts -------------------------------------------------


@respx.mock
async def test_list_accounts_sends_signed_request() -> None:
    route = respx.get(f"{_API}/accounts").mock(
        return_value=Response(200, json=[{"id": "acc_1", "currency": "BTC"}]),
    )
    node = Node(
        id="node_1",
        name="Coinbase",
        type="weftlyflow.coinbase",
        parameters={"operation": "list_accounts"},
        credentials={"coinbase_exchange": _CRED_ID},
    )
    await CoinbaseNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.headers["CB-ACCESS-KEY"] == _KEY
    assert sent.headers["CB-ACCESS-PASSPHRASE"] == _PASSPHRASE
    assert sent.headers["CB-ACCESS-SIGN"]
    assert sent.headers["CB-ACCESS-TIMESTAMP"].isdigit()


# --- get_product_ticker -------------------------------------------


@respx.mock
async def test_get_product_ticker_embeds_product_in_path() -> None:
    route = respx.get(f"{_API}/products/BTC-USD/ticker").mock(
        return_value=Response(200, json={"price": "50000.00"}),
    )
    node = Node(
        id="node_1",
        name="Coinbase",
        type="weftlyflow.coinbase",
        parameters={"operation": "get_product_ticker", "product_id": "BTC-USD"},
        credentials={"coinbase_exchange": _CRED_ID},
    )
    await CoinbaseNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- place_order ---------------------------------------------------


@respx.mock
async def test_place_limit_order_carries_price_and_size() -> None:
    route = respx.post(f"{_API}/orders").mock(
        return_value=Response(200, json={"id": "ord_1"}),
    )
    node = Node(
        id="node_1",
        name="Coinbase",
        type="weftlyflow.coinbase",
        parameters={
            "operation": "place_order",
            "product_id": "BTC-USD",
            "side": "buy",
            "order_type": "limit",
            "price": "45000.00",
            "size": "0.01",
            "time_in_force": "GTC",
        },
        credentials={"coinbase_exchange": _CRED_ID},
    )
    await CoinbaseNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["product_id"] == "BTC-USD"
    assert body["side"] == "buy"
    assert body["type"] == "limit"
    assert body["price"] == "45000.00"
    assert body["size"] == "0.01"
    assert body["time_in_force"] == "GTC"


@respx.mock
async def test_place_market_order_accepts_funds_instead_of_size() -> None:
    route = respx.post(f"{_API}/orders").mock(
        return_value=Response(200, json={"id": "ord_2"}),
    )
    node = Node(
        id="node_1",
        name="Coinbase",
        type="weftlyflow.coinbase",
        parameters={
            "operation": "place_order",
            "product_id": "BTC-USD",
            "side": "buy",
            "order_type": "market",
            "funds": "100.00",
        },
        credentials={"coinbase_exchange": _CRED_ID},
    )
    await CoinbaseNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["type"] == "market"
    assert body["funds"] == "100.00"
    assert "price" not in body


def test_place_limit_order_requires_price() -> None:
    with pytest.raises(ValueError, match="'price' is required"):
        build_request(
            "place_order",
            {
                "product_id": "BTC-USD",
                "side": "buy",
                "order_type": "limit",
                "size": "0.01",
            },
        )


def test_place_market_order_requires_size_or_funds() -> None:
    with pytest.raises(ValueError, match="'size' or 'funds'"):
        build_request(
            "place_order",
            {"product_id": "BTC-USD", "side": "buy", "order_type": "market"},
        )


def test_place_order_rejects_unknown_side() -> None:
    with pytest.raises(ValueError, match="'side' must be"):
        build_request(
            "place_order",
            {"product_id": "BTC-USD", "side": "maybe", "order_type": "market", "size": "1"},
        )


# --- cancel_order --------------------------------------------------


@respx.mock
async def test_cancel_order_uses_delete_method() -> None:
    route = respx.delete(f"{_API}/orders/ord_1").mock(
        return_value=Response(200, json={"id": "ord_1"}),
    )
    node = Node(
        id="node_1",
        name="Coinbase",
        type="weftlyflow.coinbase",
        parameters={"operation": "cancel_order", "order_id": "ord_1"},
        credentials={"coinbase_exchange": _CRED_ID},
    )
    await CoinbaseNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.get(f"{_API}/accounts").mock(
        return_value=Response(401, json={"message": "invalid signature"}),
    )
    node = Node(
        id="node_1",
        name="Coinbase",
        type="weftlyflow.coinbase",
        parameters={"operation": "list_accounts"},
        credentials={"coinbase_exchange": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid signature"):
        await CoinbaseNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Coinbase",
        type="weftlyflow.coinbase",
        parameters={"operation": "list_accounts"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await CoinbaseNode().execute(_ctx_for(node), [Item()])


async def test_empty_passphrase_raises() -> None:
    resolver = _resolver(passphrase="")
    node = Node(
        id="node_1",
        name="Coinbase",
        type="weftlyflow.coinbase",
        parameters={"operation": "list_accounts"},
        credentials={"coinbase_exchange": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'passphrase'"):
        await CoinbaseNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
