"""Unit tests for :class:`PayPalNode` and ``PayPalApiCredential``.

Exercises the distinctive runtime token-fetch (OAuth2 client
credentials grant), per-write ``PayPal-Request-Id`` idempotency
header, environment-routed host (sandbox vs live), nested
``purchase_units[0].amount`` envelope, and ``message`` /
``details[].issue`` error envelope.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PayPalApiCredential
from weftlyflow.credentials.types.paypal_api import (
    fetch_access_token,
    host_from,
)
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.paypal import PayPalNode
from weftlyflow.nodes.integrations.paypal.operations import build_request

_CRED_ID: str = "cr_paypal"
_PROJECT_ID: str = "pr_test"
_CLIENT_ID: str = "AY-test-client-id"
_CLIENT_SECRET: str = "EL-test-client-secret"
_TOKEN: str = "A21AAH-runtime-token"
_SANDBOX_BASE: str = "https://api-m.sandbox.paypal.com"


def _resolver(
    *,
    client_id: str = _CLIENT_ID,
    client_secret: str = _CLIENT_SECRET,
    environment: str = "sandbox",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.paypal_api": PayPalApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.paypal_api",
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
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


def _expected_basic() -> str:
    raw = f"{_CLIENT_ID}:{_CLIENT_SECRET}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _mock_token_endpoint() -> respx.Route:
    return respx.post(f"{_SANDBOX_BASE}/v1/oauth2/token").mock(
        return_value=Response(
            200,
            json={
                "access_token": _TOKEN,
                "token_type": "Bearer",
                "expires_in": 32400,
            },
        ),
    )


# --- host_from -------------------------------------------------------


def test_host_from_sandbox_and_live() -> None:
    assert host_from("sandbox") == "api-m.sandbox.paypal.com"
    assert host_from("live") == "api-m.paypal.com"


def test_host_from_rejects_unknown_environment() -> None:
    with pytest.raises(ValueError, match="'environment' must be one of"):
        host_from("staging")


# --- fetch_access_token + credential.inject -------------------------


@respx.mock
async def test_fetch_access_token_posts_basic_auth_and_form_body() -> None:
    route = _mock_token_endpoint()
    async with httpx.AsyncClient(base_url=_SANDBOX_BASE) as client:
        token = await fetch_access_token(
            client,
            {"client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET},
        )
    assert token == _TOKEN
    request = route.calls.last.request
    assert request.headers["Authorization"] == _expected_basic()
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert b"grant_type=client_credentials" in request.content


async def test_fetch_token_requires_client_id_and_secret() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="client_id and client_secret are required"):
            await fetch_access_token(client, {})


@respx.mock
async def test_fetch_token_raises_on_non_200() -> None:
    respx.post(f"{_SANDBOX_BASE}/v1/oauth2/token").mock(
        return_value=Response(401, json={"error": "invalid_client"}),
    )
    async with httpx.AsyncClient(base_url=_SANDBOX_BASE) as client:
        with pytest.raises(ValueError, match="rejected credentials"):
            await fetch_access_token(
                client,
                {"client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET},
            )


@respx.mock
async def test_fetch_token_raises_when_payload_missing_token() -> None:
    respx.post(f"{_SANDBOX_BASE}/v1/oauth2/token").mock(
        return_value=Response(200, json={"token_type": "Bearer"}),
    )
    async with httpx.AsyncClient(base_url=_SANDBOX_BASE) as client:
        with pytest.raises(ValueError, match="omitted 'access_token'"):
            await fetch_access_token(
                client,
                {"client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET},
            )


async def test_credential_inject_is_no_op() -> None:
    request = httpx.Request("GET", f"{_SANDBOX_BASE}/v2/checkout/orders/X")
    out = await PayPalApiCredential().inject(
        {"client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET},
        request,
    )
    assert "Authorization" not in out.headers


# --- create_order (token fetch + Bearer + idempotency) ---------------


@respx.mock
async def test_create_order_fetches_token_then_posts_with_bearer() -> None:
    _mock_token_endpoint()
    api_route = respx.post(f"{_SANDBOX_BASE}/v2/checkout/orders").mock(
        return_value=Response(201, json={"id": "ORD-1", "status": "CREATED"}),
    )
    node = Node(
        id="node_1",
        name="PayPal",
        type="weftlyflow.paypal",
        parameters={
            "operation": "create_order",
            "currency": "USD",
            "amount": "10.99",
            "request_id": "ik-fixed-1",
            "reference_id": "ref-1",
        },
        credentials={"paypal_api": _CRED_ID},
    )
    await PayPalNode().execute(_ctx_for(node), [Item()])
    request = api_route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.headers["PayPal-Request-Id"] == "ik-fixed-1"
    body = json.loads(request.content)
    assert body == {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {"currency_code": "USD", "value": "10.99"},
                "reference_id": "ref-1",
            },
        ],
    }


def test_create_order_auto_generates_request_id() -> None:
    _, _, _, _, request_id = build_request(
        "create_order",
        {"currency": "USD", "amount": "5.00"},
    )
    assert isinstance(request_id, str)
    assert len(request_id) >= 16


def test_create_order_requires_currency_and_amount() -> None:
    with pytest.raises(ValueError, match="'currency' is required"):
        build_request("create_order", {})
    with pytest.raises(ValueError, match="'amount' is required"):
        build_request("create_order", {"currency": "USD"})


# --- capture_order (POST with empty body, idempotency) --------------


@respx.mock
async def test_capture_order_posts_empty_body_with_idempotency() -> None:
    _mock_token_endpoint()
    route = respx.post(f"{_SANDBOX_BASE}/v2/checkout/orders/ORD-1/capture").mock(
        return_value=Response(201, json={"id": "ORD-1", "status": "COMPLETED"}),
    )
    node = Node(
        id="node_1",
        name="PayPal",
        type="weftlyflow.paypal",
        parameters={"operation": "capture_order", "order_id": "ORD-1"},
        credentials={"paypal_api": _CRED_ID},
    )
    await PayPalNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["PayPal-Request-Id"]
    assert json.loads(request.content) == {}


# --- refund_capture --------------------------------------------------


@respx.mock
async def test_refund_capture_includes_amount_envelope() -> None:
    _mock_token_endpoint()
    route = respx.post(f"{_SANDBOX_BASE}/v2/payments/captures/CAP-1/refund").mock(
        return_value=Response(201, json={"id": "REF-1"}),
    )
    node = Node(
        id="node_1",
        name="PayPal",
        type="weftlyflow.paypal",
        parameters={
            "operation": "refund_capture",
            "capture_id": "CAP-1",
            "amount": "5.00",
            "currency": "USD",
            "note_to_payer": "Sorry!",
        },
        credentials={"paypal_api": _CRED_ID},
    )
    await PayPalNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "amount": {"value": "5.00", "currency_code": "USD"},
        "note_to_payer": "Sorry!",
    }


# --- list/get invoices ----------------------------------------------


@respx.mock
async def test_list_invoices_uses_query_params() -> None:
    _mock_token_endpoint()
    route = respx.get(f"{_SANDBOX_BASE}/v2/invoicing/invoices").mock(
        return_value=Response(200, json={"items": []}),
    )
    node = Node(
        id="node_1",
        name="PayPal",
        type="weftlyflow.paypal",
        parameters={
            "operation": "list_invoices",
            "page": 1,
            "page_size": 25,
            "total_required": True,
        },
        credentials={"paypal_api": _CRED_ID},
    )
    await PayPalNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("page") == "1"
    assert params.get("page_size") == "25"
    assert params.get("total_required") == "true"


# --- errors ---------------------------------------------------------


@respx.mock
async def test_token_fetch_failure_raises_node_execution_error() -> None:
    respx.post(f"{_SANDBOX_BASE}/v1/oauth2/token").mock(
        return_value=Response(401, json={"error": "invalid_client"}),
    )
    node = Node(
        id="node_1",
        name="PayPal",
        type="weftlyflow.paypal",
        parameters={"operation": "get_order", "order_id": "ORD-1"},
        credentials={"paypal_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="token fetch failed"):
        await PayPalNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_api_error_envelope_is_parsed() -> None:
    _mock_token_endpoint()
    respx.get(f"{_SANDBOX_BASE}/v2/checkout/orders/ORD-X").mock(
        return_value=Response(
            404,
            json={
                "name": "RESOURCE_NOT_FOUND",
                "message": "The specified resource does not exist.",
                "details": [{"issue": "INVALID_RESOURCE_ID"}],
            },
        ),
    )
    node = Node(
        id="node_1",
        name="PayPal",
        type="weftlyflow.paypal",
        parameters={"operation": "get_order", "order_id": "ORD-X"},
        credentials={"paypal_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="resource does not exist"):
        await PayPalNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="PayPal",
        type="weftlyflow.paypal",
        parameters={"operation": "list_invoices"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await PayPalNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
