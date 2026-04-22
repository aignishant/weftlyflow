"""Unit tests for :class:`IntercomNode`.

Exercises every supported operation against a respx-mocked Intercom
REST API. Verifies Bearer authentication **and** that every request
carries the ``Intercom-Version`` header sourced from the credential.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import IntercomApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.intercom import IntercomNode
from weftlyflow.nodes.integrations.intercom.operations import build_request

_CRED_ID: str = "cr_ic"
_PROJECT_ID: str = "pr_test"
_BASE: str = "https://api.intercom.io"


def _resolver(
    *,
    access_token: str = "ic_tok",
    api_version: str = "2.11",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.intercom_api": IntercomApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.intercom_api",
                {"access_token": access_token, "api_version": api_version},
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


# --- create_contact -----------------------------------------------------


@respx.mock
async def test_create_contact_sends_bearer_and_version_headers() -> None:
    route = respx.post(f"{_BASE}/contacts").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={
            "operation": "create_contact",
            "role": "user",
            "email": "a@x.io",
            "name": "Alice",
            "custom_attributes": {"plan": "pro"},
        },
        credentials={"intercom_api": _CRED_ID},
    )
    out = await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["id"] == "c1"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer ic_tok"
    assert request.headers["intercom-version"] == "2.11"
    body = json.loads(request.content)
    assert body == {
        "role": "user",
        "email": "a@x.io",
        "name": "Alice",
        "custom_attributes": {"plan": "pro"},
    }


@respx.mock
async def test_create_contact_uses_credential_version_override() -> None:
    route = respx.post(f"{_BASE}/contacts").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={
            "operation": "create_contact",
            "role": "lead",
            "external_id": "u-99",
        },
        credentials={"intercom_api": _CRED_ID},
    )
    await IntercomNode().execute(
        _ctx_for(node, resolver=_resolver(api_version="2.10")), [Item()],
    )
    assert route.calls.last.request.headers["intercom-version"] == "2.10"


# --- update / get / search ----------------------------------------------


@respx.mock
async def test_update_contact_puts_fields() -> None:
    route = respx.put(f"{_BASE}/contacts/c1").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={
            "operation": "update_contact",
            "contact_id": "c1",
            "fields": {"name": "Alicia"},
        },
        credentials={"intercom_api": _CRED_ID},
    )
    await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "Alicia"}


@respx.mock
async def test_get_contact_is_a_get() -> None:
    route = respx.get(f"{_BASE}/contacts/c1").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={"operation": "get_contact", "contact_id": "c1"},
        credentials={"intercom_api": _CRED_ID},
    )
    await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


@respx.mock
async def test_search_contacts_surfaces_data_convenience_key() -> None:
    route = respx.post(f"{_BASE}/contacts/search").mock(
        return_value=Response(
            200, json={"total_count": 2, "data": [{"id": "c1"}, {"id": "c2"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={
            "operation": "search_contacts",
            "query": {
                "field": "email", "operator": "=", "value": "a@x.io",
            },
            "per_page": 50,
        },
        credentials={"intercom_api": _CRED_ID},
    )
    out = await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [d["id"] for d in result.json["data"]] == ["c1", "c2"]
    body = json.loads(route.calls.last.request.content)
    assert body["pagination"] == {"per_page": 50}


@respx.mock
async def test_search_contacts_caps_per_page() -> None:
    route = respx.post(f"{_BASE}/contacts/search").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={
            "operation": "search_contacts",
            "query": {"field": "email", "operator": "=", "value": "a"},
            "per_page": 9999,
        },
        credentials={"intercom_api": _CRED_ID},
    )
    await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["pagination"]["per_page"] == 150


# --- conversations -------------------------------------------------------


@respx.mock
async def test_create_conversation_wraps_contact_in_from() -> None:
    route = respx.post(f"{_BASE}/conversations").mock(
        return_value=Response(200, json={"id": "conv-1"}),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={
            "operation": "create_conversation",
            "contact_id": "c1",
            "contact_type": "user",
            "body": "Hello!",
        },
        credentials={"intercom_api": _CRED_ID},
    )
    await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"from": {"type": "user", "id": "c1"}, "body": "Hello!"}


@respx.mock
async def test_reply_conversation_admin_requires_admin_id() -> None:
    route = respx.post(f"{_BASE}/conversations/conv-1/reply").mock(
        return_value=Response(200, json={"id": "conv-1"}),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={
            "operation": "reply_conversation",
            "conversation_id": "conv-1",
            "reply_type": "admin",
            "admin_id": "5",
            "message_type": "comment",
            "body": "Thanks for reaching out",
        },
        credentials={"intercom_api": _CRED_ID},
    )
    await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "message_type": "comment",
        "type": "admin",
        "body": "Thanks for reaching out",
        "admin_id": "5",
    }


# --- error & credential paths -------------------------------------------


@respx.mock
async def test_api_error_surfaces_errors_array_code_and_message() -> None:
    respx.post(f"{_BASE}/contacts").mock(
        return_value=Response(
            400,
            json={
                "type": "error.list",
                "errors": [{"code": "parameter_invalid", "message": "email is invalid"}],
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={"operation": "create_contact", "role": "user", "email": "bogus"},
        credentials={"intercom_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="email is invalid"):
        await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={"operation": "get_contact", "contact_id": "c1"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await IntercomNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_token_raises() -> None:
    node = Node(
        id="node_1",
        name="Intercom",
        type="weftlyflow.intercom",
        parameters={"operation": "get_contact", "contact_id": "c1"},
        credentials={"intercom_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'access_token'"):
        await IntercomNode().execute(
            _ctx_for(node, resolver=_resolver(access_token="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_create_contact_requires_identifier() -> None:
    with pytest.raises(ValueError, match="'email', 'external_id', or 'phone'"):
        build_request("create_contact", {"role": "user"})


def test_build_request_reply_admin_requires_admin_id() -> None:
    with pytest.raises(ValueError, match="'admin_id' is required"):
        build_request(
            "reply_conversation",
            {
                "conversation_id": "conv-1",
                "reply_type": "admin",
                "body": "hi",
                "message_type": "comment",
            },
        )


def test_build_request_search_requires_query_object() -> None:
    with pytest.raises(ValueError, match="'query'"):
        build_request("search_contacts", {})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("merge_contacts", {})
