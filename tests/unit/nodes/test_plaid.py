"""Unit tests for :class:`PlaidNode` and ``PlaidApiCredential``.

Plaid's distinctive mechanics: ``client_id`` and ``secret`` are both
required inside **every** JSON body, and the ``environment`` field
(sandbox/development/production) chooses the target host.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PlaidApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.plaid import PlaidNode
from weftlyflow.nodes.integrations.plaid.operations import build_request

_CRED_ID: str = "cr_plaid"
_PROJECT_ID: str = "pr_test"
_CLIENT_ID: str = "cid_abc"
_SECRET: str = "sec_xyz"
_SANDBOX: str = "https://sandbox.plaid.com"
_PRODUCTION: str = "https://production.plaid.com"


def _resolver(
    *,
    client_id: str = _CLIENT_ID,
    secret: str = _SECRET,
    environment: str = "sandbox",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.plaid_api": PlaidApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.plaid_api",
                {"client_id": client_id, "secret": secret, "environment": environment},
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


# --- credential: inject is a no-op --------------------------------


async def test_credential_inject_is_no_op() -> None:
    request = httpx.Request("POST", f"{_SANDBOX}/item/get")
    out = await PlaidApiCredential().inject(
        {"client_id": _CLIENT_ID, "secret": _SECRET}, request,
    )
    assert "Authorization" not in out.headers


# --- link_token_create --------------------------------------------


@respx.mock
async def test_link_token_create_folds_client_id_and_secret_into_body() -> None:
    route = respx.post(f"{_SANDBOX}/link/token/create").mock(
        return_value=Response(200, json={"link_token": "link_xxx"}),
    )
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={
            "operation": "link_token_create",
            "client_name": "Acme",
            "client_user_id": "u_1",
            "products": ["auth", "transactions"],
            "country_codes": ["US"],
            "language": "en",
        },
        credentials={"plaid_api": _CRED_ID},
    )
    await PlaidNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["client_id"] == _CLIENT_ID
    assert body["secret"] == _SECRET
    assert body["user"] == {"client_user_id": "u_1"}
    assert body["products"] == ["auth", "transactions"]
    assert body["country_codes"] == ["US"]


def test_link_token_create_requires_products() -> None:
    with pytest.raises(ValueError, match="'products' must be a non-empty list"):
        build_request(
            "link_token_create",
            {
                "client_name": "Acme",
                "client_user_id": "u_1",
                "country_codes": ["US"],
            },
        )


def test_link_token_create_requires_country_codes() -> None:
    with pytest.raises(ValueError, match="'country_codes' must be a non-empty list"):
        build_request(
            "link_token_create",
            {
                "client_name": "Acme",
                "client_user_id": "u_1",
                "products": ["auth"],
            },
        )


# --- item_get / accounts_get --------------------------------------


@respx.mock
async def test_item_get_posts_access_token_with_credentials() -> None:
    route = respx.post(f"{_SANDBOX}/item/get").mock(
        return_value=Response(200, json={"item": {"item_id": "itm_1"}}),
    )
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={"operation": "item_get", "access_token": "acc_xxx"},
        credentials={"plaid_api": _CRED_ID},
    )
    await PlaidNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "access_token": "acc_xxx",
        "client_id": _CLIENT_ID,
        "secret": _SECRET,
    }


@respx.mock
async def test_accounts_get_forwards_options_filter() -> None:
    route = respx.post(f"{_SANDBOX}/accounts/get").mock(
        return_value=Response(200, json={"accounts": []}),
    )
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={
            "operation": "accounts_get",
            "access_token": "acc_xxx",
            "account_ids": ["a1", "a2"],
        },
        credentials={"plaid_api": _CRED_ID},
    )
    await PlaidNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["options"] == {"account_ids": ["a1", "a2"]}


# --- transactions_sync --------------------------------------------


@respx.mock
async def test_transactions_sync_passes_cursor_and_count() -> None:
    route = respx.post(f"{_SANDBOX}/transactions/sync").mock(
        return_value=Response(200, json={"added": [], "has_more": False}),
    )
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={
            "operation": "transactions_sync",
            "access_token": "acc_xxx",
            "cursor": "cur_123",
            "count": 100,
        },
        credentials={"plaid_api": _CRED_ID},
    )
    await PlaidNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["cursor"] == "cur_123"
    assert body["count"] == 100


@respx.mock
async def test_transactions_sync_omits_cursor_on_initial_sync() -> None:
    route = respx.post(f"{_SANDBOX}/transactions/sync").mock(
        return_value=Response(200, json={"added": [], "has_more": False}),
    )
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={
            "operation": "transactions_sync",
            "access_token": "acc_xxx",
        },
        credentials={"plaid_api": _CRED_ID},
    )
    await PlaidNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert "cursor" not in body


# --- environment routing ------------------------------------------


@respx.mock
async def test_environment_field_routes_to_production_host() -> None:
    route = respx.post(f"{_PRODUCTION}/item/get").mock(
        return_value=Response(200, json={"item": {"item_id": "itm_1"}}),
    )
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={"operation": "item_get", "access_token": "acc_xxx"},
        credentials={"plaid_api": _CRED_ID},
    )
    await PlaidNode().execute(
        _ctx_for(node, resolver=_resolver(environment="production")), [Item()],
    )
    assert route.called


# --- errors --------------------------------------------------------


@respx.mock
async def test_plaid_error_message_is_parsed() -> None:
    respx.post(f"{_SANDBOX}/item/get").mock(
        return_value=Response(
            400,
            json={
                "error_code": "INVALID_ACCESS_TOKEN",
                "error_message": "access token is invalid",
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={"operation": "item_get", "access_token": "bad"},
        credentials={"plaid_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="access token is invalid"):
        await PlaidNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={"operation": "item_get", "access_token": "acc_xxx"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await PlaidNode().execute(_ctx_for(node), [Item()])


async def test_empty_client_id_raises() -> None:
    resolver = _resolver(client_id="")
    node = Node(
        id="node_1",
        name="Plaid",
        type="weftlyflow.plaid",
        parameters={"operation": "item_get", "access_token": "acc_xxx"},
        credentials={"plaid_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'client_id' or 'secret'"):
        await PlaidNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
