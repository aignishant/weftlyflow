"""Unit tests for :class:`ZendeskNode`.

Exercises every supported operation against a respx-mocked Zendesk
Support v2 REST API. Verifies Basic auth with the ``<email>/token``
username suffix and per-tenant subdomain host, plus the ``ticket`` /
``tickets`` envelope shape Zendesk expects.
"""

from __future__ import annotations

import base64
import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ZendeskApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.zendesk import ZendeskNode
from weftlyflow.nodes.integrations.zendesk.operations import build_request

_CRED_ID: str = "cr_zd"
_PROJECT_ID: str = "pr_test"
_SUBDOMAIN: str = "acme"
_BASE: str = f"https://{_SUBDOMAIN}.zendesk.com/api/v2"


def _resolver(
    *,
    subdomain: str = _SUBDOMAIN,
    email: str = "support@acme.io",
    api_token: str = "ztk_abc",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.zendesk_api": ZendeskApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.zendesk_api",
                {"subdomain": subdomain, "email": email, "api_token": api_token},
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


def _expected_basic(email: str, token: str) -> str:
    return "Basic " + base64.b64encode(
        f"{email}/token:{token}".encode(),
    ).decode("ascii")


# --- get_ticket ---------------------------------------------------------


@respx.mock
async def test_get_ticket_uses_basic_auth_with_token_suffix() -> None:
    route = respx.get(f"{_BASE}/tickets/123.json").mock(
        return_value=Response(200, json={"ticket": {"id": 123}}),
    )
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={"operation": "get_ticket", "ticket_id": 123},
        credentials={"zendesk_api": _CRED_ID},
    )
    out = await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["ticket"]["id"] == 123
    request = route.calls.last.request
    assert request.headers["authorization"] == _expected_basic(
        "support@acme.io", "ztk_abc",
    )


async def test_get_ticket_rejects_non_integer_id() -> None:
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={"operation": "get_ticket", "ticket_id": "abc"},
        credentials={"zendesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'ticket_id' must be an integer"):
        await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- create_ticket ------------------------------------------------------


@respx.mock
async def test_create_ticket_wraps_payload_in_ticket_envelope() -> None:
    route = respx.post(f"{_BASE}/tickets.json").mock(
        return_value=Response(201, json={"ticket": {"id": 9}}),
    )
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={
            "operation": "create_ticket",
            "subject": "Broken widget",
            "comment": "Please help",
            "priority": "high",
            "extra_fields": {"tags": ["widget", "urgent"]},
        },
        credentials={"zendesk_api": _CRED_ID},
    )
    await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "ticket": {
            "subject": "Broken widget",
            "comment": {"body": "Please help"},
            "priority": "high",
            "tags": ["widget", "urgent"],
        },
    }


async def test_create_ticket_rejects_invalid_priority() -> None:
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={
            "operation": "create_ticket",
            "subject": "x",
            "comment": "y",
            "priority": "blocker",
        },
        credentials={"zendesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid priority"):
        await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_create_ticket_rejects_unknown_extra_field() -> None:
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={
            "operation": "create_ticket",
            "subject": "x",
            "comment": "y",
            "extra_fields": {"totally_made_up": True},
        },
        credentials={"zendesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unknown create ticket field"):
        await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- update_ticket ------------------------------------------------------


@respx.mock
async def test_update_ticket_puts_fields_under_ticket_key() -> None:
    route = respx.put(f"{_BASE}/tickets/42.json").mock(
        return_value=Response(200, json={"ticket": {"id": 42}}),
    )
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={
            "operation": "update_ticket",
            "ticket_id": 42,
            "fields": {"status": "solved", "priority": "low"},
        },
        credentials={"zendesk_api": _CRED_ID},
    )
    await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"ticket": {"status": "solved", "priority": "low"}}


async def test_update_ticket_rejects_invalid_status() -> None:
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={
            "operation": "update_ticket",
            "ticket_id": 1,
            "fields": {"status": "archived"},
        },
        credentials={"zendesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid status"):
        await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- list_tickets / add_comment / search --------------------------------


@respx.mock
async def test_list_tickets_caps_per_page_and_surfaces_results() -> None:
    route = respx.get(f"{_BASE}/tickets.json").mock(
        return_value=Response(
            200, json={"tickets": [{"id": 1}, {"id": 2}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={"operation": "list_tickets", "per_page": 9999, "page": 2},
        credentials={"zendesk_api": _CRED_ID},
    )
    out = await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [t["id"] for t in result.json["results"]] == [1, 2]
    url = str(route.calls.last.request.url)
    assert "per_page=100" in url
    assert "page=2" in url


@respx.mock
async def test_add_comment_patches_ticket_with_public_flag() -> None:
    route = respx.put(f"{_BASE}/tickets/7.json").mock(
        return_value=Response(200, json={"ticket": {"id": 7}}),
    )
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={
            "operation": "add_comment",
            "ticket_id": 7,
            "comment": "Ack",
            "public": False,
        },
        credentials={"zendesk_api": _CRED_ID},
    )
    await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "ticket": {"comment": {"body": "Ack", "public": False}},
    }


@respx.mock
async def test_search_surfaces_results_and_sort_params() -> None:
    route = respx.get(f"{_BASE}/search.json").mock(
        return_value=Response(
            200, json={"results": [{"id": 99, "type": "ticket"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={
            "operation": "search",
            "query": "status:open type:ticket",
            "sort_by": "created_at",
            "sort_order": "desc",
        },
        credentials={"zendesk_api": _CRED_ID},
    )
    out = await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["results"][0]["id"] == 99
    url = str(route.calls.last.request.url)
    assert "query=status%3Aopen+type%3Aticket" in url
    assert "sort_by=created_at" in url
    assert "sort_order=desc" in url


# --- error handling -----------------------------------------------------


@respx.mock
async def test_api_error_surfaces_description() -> None:
    respx.post(f"{_BASE}/tickets.json").mock(
        return_value=Response(
            422, json={"description": "Subject: cannot be blank"},
        ),
    )
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={
            "operation": "create_ticket",
            "subject": "x",
            "comment": "y",
        },
        credentials={"zendesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Subject: cannot be blank"):
        await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_subdomain_raises() -> None:
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={"operation": "get_ticket", "ticket_id": 1},
        credentials={"zendesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="subdomain"):
        await ZendeskNode().execute(
            _ctx_for(node, resolver=_resolver(subdomain="")), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Zendesk",
        type="weftlyflow.zendesk",
        parameters={"operation": "get_ticket", "ticket_id": 1},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await ZendeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- direct builder unit tests ------------------------------------------


def test_build_request_search_requires_query() -> None:
    with pytest.raises(ValueError, match="'query'"):
        build_request("search", {})


def test_build_request_update_needs_non_empty_fields() -> None:
    with pytest.raises(ValueError, match="'fields'"):
        build_request("update_ticket", {"ticket_id": 1, "fields": {}})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_ticket", {})
