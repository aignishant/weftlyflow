"""Unit tests for :class:`StripeNode`.

Exercises every supported operation against a respx-mocked Stripe REST
API. Validates form-encoded request bodies, bracketed metadata keys, and
Idempotency-Key header propagation.
"""

from __future__ import annotations

from urllib.parse import parse_qs

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BearerTokenCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.stripe import StripeNode
from weftlyflow.nodes.integrations.stripe.operations import build_request

_CRED_ID: str = "cr_stripe"
_PROJECT_ID: str = "pr_test"


def _resolver(*, token: str = "sk_test_abc") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.bearer_token": BearerTokenCredential},
        rows={_CRED_ID: ("weftlyflow.bearer_token", {"token": token}, _PROJECT_ID)},
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


def _form(body_bytes: bytes) -> dict[str, list[str]]:
    return parse_qs(body_bytes.decode())


# --- create_customer -------------------------------------------------------


@respx.mock
async def test_create_customer_sends_form_encoded_body_and_metadata() -> None:
    route = respx.post("https://api.stripe.com/v1/customers").mock(
        return_value=Response(200, json={"id": "cus_1", "email": "ada@example.com"}),
    )
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={
            "operation": "create_customer",
            "email": "ada@example.com",
            "name": "Ada",
            "metadata": {"source": "signup", "plan": "pro"},
            "idempotency_key": "req_1",
        },
        credentials={"stripe_api": _CRED_ID},
    )
    out = await StripeNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["id"] == "cus_1"
    form = _form(route.calls.last.request.content)
    assert form["email"] == ["ada@example.com"]
    assert form["name"] == ["Ada"]
    assert form["metadata[source]"] == ["signup"]
    assert form["metadata[plan]"] == ["pro"]
    headers = route.calls.last.request.headers
    assert headers["authorization"] == "Bearer sk_test_abc"
    assert headers["content-type"] == "application/x-www-form-urlencoded"
    assert headers["idempotency-key"] == "req_1"


@respx.mock
async def test_create_customer_without_any_identifier_raises() -> None:
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={"operation": "create_customer"},
        credentials={"stripe_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="at least one"):
        await StripeNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- list_customers --------------------------------------------------------


@respx.mock
async def test_list_customers_uses_query_params() -> None:
    route = respx.get("https://api.stripe.com/v1/customers").mock(
        return_value=Response(
            200, json={"data": [{"id": "cus_1"}], "has_more": False},
        ),
    )
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={
            "operation": "list_customers",
            "email": "ada@example.com",
            "limit": 25,
            "starting_after": "cus_0",
        },
        credentials={"stripe_api": _CRED_ID},
    )
    await StripeNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    query = dict(route.calls.last.request.url.params)
    assert query["email"] == "ada@example.com"
    assert query["limit"] == "25"
    assert query["starting_after"] == "cus_0"


@respx.mock
async def test_list_customers_caps_limit_at_max() -> None:
    route = respx.get("https://api.stripe.com/v1/customers").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={"operation": "list_customers", "limit": 9999},
        credentials={"stripe_api": _CRED_ID},
    )
    await StripeNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.calls.last.request.url.params["limit"] == "100"


# --- create_payment_intent -------------------------------------------------


@respx.mock
async def test_create_payment_intent_posts_amount_currency_and_methods() -> None:
    route = respx.post("https://api.stripe.com/v1/payment_intents").mock(
        return_value=Response(
            200, json={"id": "pi_1", "status": "requires_payment_method"},
        ),
    )
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={
            "operation": "create_payment_intent",
            "amount": 2000,
            "currency": "USD",
            "customer": "cus_1",
            "description": "order 123",
            "payment_method_types": "card, us_bank_account",
            "metadata": {"order_id": "ord_42"},
        },
        credentials={"stripe_api": _CRED_ID},
    )
    await StripeNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    form = _form(route.calls.last.request.content)
    assert form["amount"] == ["2000"]
    assert form["currency"] == ["usd"]
    assert form["customer"] == ["cus_1"]
    assert form["description"] == ["order 123"]
    assert form["payment_method_types[0]"] == ["card"]
    assert form["payment_method_types[1]"] == ["us_bank_account"]
    assert form["metadata[order_id]"] == ["ord_42"]


@respx.mock
async def test_create_payment_intent_without_amount_raises() -> None:
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={"operation": "create_payment_intent", "currency": "usd"},
        credentials={"stripe_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="amount"):
        await StripeNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- error paths -----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_error_message() -> None:
    respx.post("https://api.stripe.com/v1/customers").mock(
        return_value=Response(
            400,
            json={"error": {"message": "Invalid email address"}},
        ),
    )
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={"operation": "create_customer", "email": "bad"},
        credentials={"stripe_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Invalid email address"):
        await StripeNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={"operation": "list_customers"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await StripeNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_secret_key_raises() -> None:
    node = Node(
        id="node_1",
        name="Stripe",
        type="weftlyflow.stripe",
        parameters={"operation": "list_customers"},
        credentials={"stripe_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'token'"):
        await StripeNode().execute(
            _ctx_for(node, resolver=_resolver(token="")), [Item()],
        )


# --- direct builder unit tests --------------------------------------------


def test_build_request_metadata_must_be_object() -> None:
    with pytest.raises(ValueError, match="metadata"):
        build_request(
            "create_customer",
            {"email": "ada@example.com", "metadata": "not-an-object"},
        )


def test_build_request_payment_intent_requires_currency() -> None:
    with pytest.raises(ValueError, match="currency"):
        build_request(
            "create_payment_intent",
            {"amount": 1000, "currency": ""},
        )


def test_build_request_payment_intent_rejects_non_positive_amount() -> None:
    with pytest.raises(ValueError, match="amount"):
        build_request(
            "create_payment_intent",
            {"amount": 0, "currency": "usd"},
        )


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
