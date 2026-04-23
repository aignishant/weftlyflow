"""Unit tests for :class:`QuickBooksNode`.

Exercises every supported operation against a respx-mocked QuickBooks
v3 API. Verifies the distinctive ``/v3/company/{realmId}`` URL prefix,
the optional ``minorversion`` query param, and the QBO-specific
``Fault.Error[].Detail`` error envelope parse.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import QuickBooksOAuth2Credential
from weftlyflow.credentials.types.quickbooks_oauth2 import host_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.quickbooks import QuickBooksNode
from weftlyflow.nodes.integrations.quickbooks.operations import build_request

_CRED_ID: str = "cr_qbo"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "qbo-access-token"
_REALM: str = "1234567890"
_BASE: str = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{_REALM}"


def _resolver(
    *,
    token: str = _TOKEN,
    realm: str = _REALM,
    environment: str = "sandbox",
    minor_version: str = "",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.quickbooks_oauth2": QuickBooksOAuth2Credential},
        rows={
            _CRED_ID: (
                "weftlyflow.quickbooks_oauth2",
                {
                    "access_token": token,
                    "realm_id": realm,
                    "environment": environment,
                    "minor_version": minor_version,
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
    assert host_from("sandbox") == "sandbox-quickbooks.api.intuit.com"
    assert host_from("production") == "quickbooks.api.intuit.com"


def test_host_from_rejects_unknown_environment() -> None:
    with pytest.raises(ValueError, match="'environment' must be one of"):
        host_from("staging")


# --- query -----------------------------------------------------------


@respx.mock
async def test_query_uses_query_param() -> None:
    route = respx.get(f"{_BASE}/query").mock(
        return_value=Response(200, json={"QueryResponse": {}}),
    )
    node = Node(
        id="node_1",
        name="QBO",
        type="weftlyflow.quickbooks",
        parameters={
            "operation": "query",
            "query": "SELECT * FROM Customer",
        },
        credentials={"quickbooks_oauth2": _CRED_ID},
    )
    await QuickBooksNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.url.params.get("query") == "SELECT * FROM Customer"


def test_query_requires_query_text() -> None:
    with pytest.raises(ValueError, match="'query' is required"):
        build_request("query", {})


# --- get_invoice / get_customer --------------------------------------


@respx.mock
async def test_get_invoice_hits_resource_path() -> None:
    respx.get(f"{_BASE}/invoice/INV-1").mock(
        return_value=Response(200, json={"Invoice": {"Id": "INV-1"}}),
    )
    node = Node(
        id="node_1",
        name="QBO",
        type="weftlyflow.quickbooks",
        parameters={"operation": "get_invoice", "invoice_id": "INV-1"},
        credentials={"quickbooks_oauth2": _CRED_ID},
    )
    await QuickBooksNode().execute(_ctx_for(node), [Item()])


def test_get_invoice_requires_invoice_id() -> None:
    with pytest.raises(ValueError, match="'invoice_id' is required"):
        build_request("get_invoice", {})


@respx.mock
async def test_get_customer_hits_resource_path() -> None:
    respx.get(f"{_BASE}/customer/C-1").mock(
        return_value=Response(200, json={"Customer": {"Id": "C-1"}}),
    )
    node = Node(
        id="node_1",
        name="QBO",
        type="weftlyflow.quickbooks",
        parameters={"operation": "get_customer", "customer_id": "C-1"},
        credentials={"quickbooks_oauth2": _CRED_ID},
    )
    await QuickBooksNode().execute(_ctx_for(node), [Item()])


# --- create_invoice / create_customer --------------------------------


@respx.mock
async def test_create_invoice_posts_naked_body() -> None:
    route = respx.post(f"{_BASE}/invoice").mock(
        return_value=Response(200, json={"Invoice": {"Id": "x"}}),
    )
    document = {"Line": [{"Amount": 100.0}]}
    node = Node(
        id="node_1",
        name="QBO",
        type="weftlyflow.quickbooks",
        parameters={"operation": "create_invoice", "document": document},
        credentials={"quickbooks_oauth2": _CRED_ID},
    )
    await QuickBooksNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == document


def test_create_customer_requires_document() -> None:
    with pytest.raises(ValueError, match="'document' is required"):
        build_request("create_customer", {})


def test_create_customer_rejects_non_dict() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        build_request("create_customer", {"document": "nope"})


# --- minor_version ---------------------------------------------------


@respx.mock
async def test_minor_version_appended_as_query_param() -> None:
    route = respx.get(f"{_BASE}/customer/C-1").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="QBO",
        type="weftlyflow.quickbooks",
        parameters={"operation": "get_customer", "customer_id": "C-1"},
        credentials={"quickbooks_oauth2": _CRED_ID},
    )
    ctx = _ctx_for(node, resolver=_resolver(minor_version="65"))
    await QuickBooksNode().execute(ctx, [Item()])
    assert route.calls.last.request.url.params.get("minorversion") == "65"


# --- errors ----------------------------------------------------------


@respx.mock
async def test_fault_error_envelope_is_parsed() -> None:
    respx.get(f"{_BASE}/customer/C-1").mock(
        return_value=Response(
            400,
            json={
                "Fault": {
                    "Error": [
                        {"Detail": "Invalid customer id", "code": "1000"},
                    ],
                },
            },
        ),
    )
    node = Node(
        id="node_1",
        name="QBO",
        type="weftlyflow.quickbooks",
        parameters={"operation": "get_customer", "customer_id": "C-1"},
        credentials={"quickbooks_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Invalid customer id"):
        await QuickBooksNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="QBO",
        type="weftlyflow.quickbooks",
        parameters={"operation": "query", "query": "SELECT * FROM Customer"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await QuickBooksNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
