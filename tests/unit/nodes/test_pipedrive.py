"""Unit tests for :class:`PipedriveNode`.

Exercises every supported operation against a respx-mocked Pipedrive
v1 REST API. Verifies the ``?api_token=`` query-string auth (there is
no ``Authorization`` header), the tenant subdomain composed from the
credential's ``company_domain``, and the deal/person/activity body
shapes.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PipedriveApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.pipedrive import PipedriveNode
from weftlyflow.nodes.integrations.pipedrive.operations import build_request

_CRED_ID: str = "cr_pd"
_PROJECT_ID: str = "pr_test"
_COMPANY: str = "acme"
_BASE: str = f"https://{_COMPANY}.pipedrive.com/api/v1"


def _resolver(
    *,
    api_token: str = "tkn-123",
    company_domain: str = _COMPANY,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.pipedrive_api": PipedriveApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.pipedrive_api",
                {"api_token": api_token, "company_domain": company_domain},
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


# --- list_deals ---------------------------------------------------------


@respx.mock
async def test_list_deals_appends_api_token_query_param_no_header() -> None:
    route = respx.get(f"{_BASE}/deals").mock(
        return_value=Response(200, json={"data": [{"id": 1}]}),
    )
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={
            "operation": "list_deals",
            "limit": 25,
            "status": "open",
        },
        credentials={"pipedrive_api": _CRED_ID},
    )
    out = await PipedriveNode().execute(
        _ctx_for(node, resolver=_resolver()), [Item()],
    )
    request = route.calls.last.request
    assert "authorization" not in request.headers
    query = str(request.url)
    assert "api_token=tkn-123" in query
    assert "limit=25" in query
    assert "status=open" in query
    [result] = out[0]
    assert result.json["data"] == [{"id": 1}]


async def test_list_deals_rejects_invalid_status() -> None:
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={"operation": "list_deals", "status": "bogus"},
        credentials={"pipedrive_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid deal status"):
        await PipedriveNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- get_deal -----------------------------------------------------------


@respx.mock
async def test_get_deal_targets_tenant_host() -> None:
    route = respx.get(f"{_BASE}/deals/99").mock(
        return_value=Response(200, json={"data": {"id": 99}}),
    )
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={"operation": "get_deal", "deal_id": 99},
        credentials={"pipedrive_api": _CRED_ID},
    )
    await PipedriveNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


async def test_get_deal_rejects_non_integer_id() -> None:
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={"operation": "get_deal", "deal_id": "abc"},
        credentials={"pipedrive_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'deal_id'"):
        await PipedriveNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- create_deal --------------------------------------------------------


@respx.mock
async def test_create_deal_posts_coerced_fk_fields() -> None:
    route = respx.post(f"{_BASE}/deals").mock(
        return_value=Response(201, json={"data": {"id": 7}}),
    )
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={
            "operation": "create_deal",
            "title": "Enterprise",
            "value": 5000,
            "currency": "USD",
            "status": "open",
            "person_id": "12",
            "org_id": "34",
        },
        credentials={"pipedrive_api": _CRED_ID},
    )
    await PipedriveNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "title": "Enterprise",
        "value": 5000,
        "currency": "USD",
        "status": "open",
        "person_id": 12,
        "org_id": 34,
    }


# --- update_deal --------------------------------------------------------


@respx.mock
async def test_update_deal_puts_patch_fields() -> None:
    route = respx.put(f"{_BASE}/deals/9").mock(
        return_value=Response(200, json={"data": {"id": 9}}),
    )
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={
            "operation": "update_deal",
            "deal_id": 9,
            "fields": {"status": "won", "value": 7000},
        },
        credentials={"pipedrive_api": _CRED_ID},
    )
    await PipedriveNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"status": "won", "value": 7000}


async def test_update_deal_rejects_unknown_field() -> None:
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={
            "operation": "update_deal",
            "deal_id": 9,
            "fields": {"bogus": "x"},
        },
        credentials={"pipedrive_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unknown deal field"):
        await PipedriveNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- create_person / create_activity ------------------------------------


@respx.mock
async def test_create_person_coerces_emails_and_phones() -> None:
    route = respx.post(f"{_BASE}/persons").mock(
        return_value=Response(201, json={"data": {"id": 3}}),
    )
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={
            "operation": "create_person",
            "name": "Nishant",
            "emails": "a@x.io, b@x.io",
            "phones": ["+1-555"],
            "org_id": 42,
        },
        credentials={"pipedrive_api": _CRED_ID},
    )
    await PipedriveNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "name": "Nishant",
        "email": ["a@x.io", "b@x.io"],
        "phone": ["+1-555"],
        "org_id": 42,
    }


@respx.mock
async def test_create_activity_posts_typed_body() -> None:
    route = respx.post(f"{_BASE}/activities").mock(
        return_value=Response(201, json={"data": {"id": 11}}),
    )
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={
            "operation": "create_activity",
            "subject": "Follow-up",
            "type": "call",
            "due_date": "2026-05-01",
            "due_time": "10:00",
            "deal_id": 9,
        },
        credentials={"pipedrive_api": _CRED_ID},
    )
    await PipedriveNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "subject": "Follow-up",
        "type": "call",
        "due_date": "2026-05-01",
        "due_time": "10:00",
        "deal_id": 9,
    }


# --- errors / credentials -----------------------------------------------


@respx.mock
async def test_api_error_surfaces_error_info() -> None:
    respx.get(f"{_BASE}/deals").mock(
        return_value=Response(
            401,
            json={"error": "Unauthorized", "error_info": "invalid token"},
        ),
    )
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={"operation": "list_deals"},
        credentials={"pipedrive_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid token"):
        await PipedriveNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={"operation": "list_deals"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await PipedriveNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_empty_company_domain_raises() -> None:
    node = Node(
        id="node_1",
        name="Pipedrive",
        type="weftlyflow.pipedrive",
        parameters={"operation": "list_deals"},
        credentials={"pipedrive_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="company_domain"):
        await PipedriveNode().execute(
            _ctx_for(node, resolver=_resolver(company_domain="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_list_caps_limit_at_max() -> None:
    _, _, _, query = build_request("list_deals", {"limit": 9_999})
    assert query["limit"] == 500


def test_build_request_update_requires_fields() -> None:
    with pytest.raises(ValueError, match="'fields'"):
        build_request("update_deal", {"deal_id": 1})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_deal", {})
