"""Unit tests for :class:`XeroNode`.

Exercises every supported operation against a respx-mocked Xero
Accounting API. Verifies the distinctive mandatory ``xero-tenant-id``
header, the ``{"Invoices": [...]}`` envelope wrapper for create/update,
page_size cap at 100, and the Xero-specific ``Elements[].ValidationErrors``
error-envelope parse.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import XeroApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.xero import XeroNode
from weftlyflow.nodes.integrations.xero.operations import build_request

_CRED_ID: str = "cr_xero"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "xero-access-token"
_TENANT: str = "00000000-0000-0000-0000-000000000001"
_BASE: str = "https://api.xero.com/api.xro/2.0"


def _resolver(
    *,
    token: str = _TOKEN,
    tenant: str = _TENANT,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.xero_api": XeroApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.xero_api",
                {"access_token": token, "tenant_id": tenant},
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


# --- list_invoices ---------------------------------------------------


@respx.mock
async def test_list_invoices_sends_tenant_header() -> None:
    route = respx.get(f"{_BASE}/Invoices").mock(
        return_value=Response(200, json={"Invoices": []}),
    )
    node = Node(
        id="node_1",
        name="Xero",
        type="weftlyflow.xero",
        parameters={
            "operation": "list_invoices",
            "statuses": "AUTHORISED",
            "page": 1,
            "page_size": 50,
        },
        credentials={"xero_api": _CRED_ID},
    )
    await XeroNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.headers["xero-tenant-id"] == _TENANT
    params = request.url.params
    assert params.get("Statuses") == "AUTHORISED"
    assert params.get("page") == "1"
    assert params.get("pageSize") == "50"


def test_list_invoices_caps_page_size_at_100() -> None:
    _, _, _, query = build_request("list_invoices", {"page_size": 500})
    assert query["pageSize"] == 100


# --- get_invoice -----------------------------------------------------


@respx.mock
async def test_get_invoice_hits_resource_path() -> None:
    respx.get(f"{_BASE}/Invoices/INV-001").mock(
        return_value=Response(200, json={"Invoices": [{"InvoiceID": "INV-001"}]}),
    )
    node = Node(
        id="node_1",
        name="Xero",
        type="weftlyflow.xero",
        parameters={"operation": "get_invoice", "invoice_id": "INV-001"},
        credentials={"xero_api": _CRED_ID},
    )
    await XeroNode().execute(_ctx_for(node), [Item()])


def test_get_invoice_requires_invoice_id() -> None:
    with pytest.raises(ValueError, match="'invoice_id' is required"):
        build_request("get_invoice", {})


# --- create_invoice --------------------------------------------------


@respx.mock
async def test_create_invoice_wraps_in_invoices_envelope() -> None:
    route = respx.post(f"{_BASE}/Invoices").mock(
        return_value=Response(200, json={"Invoices": []}),
    )
    node = Node(
        id="node_1",
        name="Xero",
        type="weftlyflow.xero",
        parameters={
            "operation": "create_invoice",
            "document": {
                "Type": "ACCREC",
                "Contact": {"ContactID": "c1"},
                "LineItems": [{"Description": "x"}],
            },
        },
        credentials={"xero_api": _CRED_ID},
    )
    await XeroNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "Invoices": [
            {
                "Type": "ACCREC",
                "Contact": {"ContactID": "c1"},
                "LineItems": [{"Description": "x"}],
            },
        ],
    }


def test_create_invoice_requires_document() -> None:
    with pytest.raises(ValueError, match="'document' is required"):
        build_request("create_invoice", {})


def test_create_invoice_rejects_non_dict_document() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        build_request("create_invoice", {"document": "not a dict"})


# --- update_invoice (POST with id) ----------------------------------


@respx.mock
async def test_update_invoice_posts_to_id_path() -> None:
    route = respx.post(f"{_BASE}/Invoices/INV-42").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="Xero",
        type="weftlyflow.xero",
        parameters={
            "operation": "update_invoice",
            "invoice_id": "INV-42",
            "document": {"Status": "AUTHORISED"},
        },
        credentials={"xero_api": _CRED_ID},
    )
    await XeroNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "POST"
    body = json.loads(route.calls.last.request.content)
    assert body == {"Invoices": [{"Status": "AUTHORISED"}]}


# --- list_contacts / list_accounts ----------------------------------


@respx.mock
async def test_list_contacts_passes_ids_filter() -> None:
    route = respx.get(f"{_BASE}/Contacts").mock(
        return_value=Response(200, json={"Contacts": []}),
    )
    node = Node(
        id="node_1",
        name="Xero",
        type="weftlyflow.xero",
        parameters={
            "operation": "list_contacts",
            "ids": "a,b,c",
            "where": 'Name=="Acme"',
        },
        credentials={"xero_api": _CRED_ID},
    )
    await XeroNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("IDs") == "a,b,c"
    assert params.get("where") == 'Name=="Acme"'


@respx.mock
async def test_list_accounts_sends_where_clause() -> None:
    respx.get(f"{_BASE}/Accounts").mock(
        return_value=Response(200, json={"Accounts": []}),
    )
    node = Node(
        id="node_1",
        name="Xero",
        type="weftlyflow.xero",
        parameters={
            "operation": "list_accounts",
            "where": 'Type=="BANK"',
        },
        credentials={"xero_api": _CRED_ID},
    )
    await XeroNode().execute(_ctx_for(node), [Item()])


# --- errors ----------------------------------------------------------


@respx.mock
async def test_validation_error_is_parsed_from_elements() -> None:
    respx.post(f"{_BASE}/Invoices").mock(
        return_value=Response(
            400,
            json={
                "Elements": [
                    {
                        "ValidationErrors": [
                            {"Message": "Contact is required"},
                        ],
                    },
                ],
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Xero",
        type="weftlyflow.xero",
        parameters={
            "operation": "create_invoice",
            "document": {"Type": "ACCREC"},
        },
        credentials={"xero_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Contact is required"):
        await XeroNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Xero",
        type="weftlyflow.xero",
        parameters={"operation": "list_invoices"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await XeroNode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
