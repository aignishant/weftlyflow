"""Unit tests for :class:`HubSpotNode`.

Exercises every supported operation against a respx-mocked HubSpot CRM
v3 contacts API. Verifies Bearer authentication, JSON ``properties``
payloads on create/update, and the ``results`` convenience key on
``search_contacts``.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import HubSpotPrivateAppCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.hubspot import HubSpotNode
from weftlyflow.nodes.integrations.hubspot.operations import build_request

_CRED_ID: str = "cr_hs"
_PROJECT_ID: str = "pr_test"
_CONTACTS_URL: str = "https://api.hubapi.com/crm/v3/objects/contacts"
_SEARCH_URL: str = "https://api.hubapi.com/crm/v3/objects/contacts/search"


def _resolver(*, access_token: str = "pat_hs") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.hubspot_private_app": HubSpotPrivateAppCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.hubspot_private_app",
                {"access_token": access_token},
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


# --- create_contact ------------------------------------------------------


@respx.mock
async def test_create_contact_posts_properties_with_bearer() -> None:
    route = respx.post(_CONTACTS_URL).mock(
        return_value=Response(201, json={"id": "1", "properties": {"email": "a@x"}}),
    )
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={
            "operation": "create_contact",
            "properties": {"email": "a@x", "firstname": "A"},
        },
        credentials={"hubspot_api": _CRED_ID},
    )
    out = await HubSpotNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["id"] == "1"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer pat_hs"
    body = json.loads(request.content)
    assert body == {"properties": {"email": "a@x", "firstname": "A"}}


# --- update / get / delete ----------------------------------------------


@respx.mock
async def test_update_contact_patches_properties() -> None:
    route = respx.patch(f"{_CONTACTS_URL}/42").mock(
        return_value=Response(200, json={"id": "42"}),
    )
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={
            "operation": "update_contact",
            "contact_id": "42",
            "properties": {"lifecyclestage": "customer"},
        },
        credentials={"hubspot_api": _CRED_ID},
    )
    await HubSpotNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"properties": {"lifecyclestage": "customer"}}


@respx.mock
async def test_get_contact_forwards_property_list_as_csv() -> None:
    route = respx.get(f"{_CONTACTS_URL}/42").mock(
        return_value=Response(200, json={"id": "42"}),
    )
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={
            "operation": "get_contact",
            "contact_id": "42",
            "properties": ["email", "firstname"],
        },
        credentials={"hubspot_api": _CRED_ID},
    )
    await HubSpotNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    query = dict(route.calls.last.request.url.params)
    assert query["properties"] == "email,firstname"


@respx.mock
async def test_delete_contact_is_a_delete() -> None:
    route = respx.delete(f"{_CONTACTS_URL}/42").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={"operation": "delete_contact", "contact_id": "42"},
        credentials={"hubspot_api": _CRED_ID},
    )
    out = await HubSpotNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["status"] == 204
    assert route.called


# --- search_contacts ------------------------------------------------------


@respx.mock
async def test_search_contacts_surfaces_results_convenience_key() -> None:
    route = respx.post(_SEARCH_URL).mock(
        return_value=Response(
            200,
            json={"total": 2, "results": [{"id": "1"}, {"id": "2"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={
            "operation": "search_contacts",
            "query": "acme",
            "limit": 25,
            "properties": "email,firstname",
        },
        credentials={"hubspot_api": _CRED_ID},
    )
    out = await HubSpotNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [r["id"] for r in result.json["results"]] == ["1", "2"]
    body = json.loads(route.calls.last.request.content)
    assert body["query"] == "acme"
    assert body["limit"] == 25
    assert body["properties"] == ["email", "firstname"]


@respx.mock
async def test_search_contacts_caps_limit_at_100() -> None:
    route = respx.post(_SEARCH_URL).mock(return_value=Response(200, json={}))
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={"operation": "search_contacts", "limit": 9999},
        credentials={"hubspot_api": _CRED_ID},
    )
    await HubSpotNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["limit"] == 100


# --- error paths ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_message() -> None:
    respx.post(_CONTACTS_URL).mock(
        return_value=Response(
            400,
            json={"message": "property does not exist", "category": "VALIDATION_ERROR"},
        ),
    )
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={
            "operation": "create_contact",
            "properties": {"bogus": "x"},
        },
        credentials={"hubspot_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="property does not exist"):
        await HubSpotNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={"operation": "get_contact", "contact_id": "1"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await HubSpotNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_access_token_raises() -> None:
    node = Node(
        id="node_1",
        name="HubSpot",
        type="weftlyflow.hubspot",
        parameters={"operation": "get_contact", "contact_id": "1"},
        credentials={"hubspot_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'access_token'"):
        await HubSpotNode().execute(
            _ctx_for(node, resolver=_resolver(access_token="")), [Item()],
        )


# --- direct builder unit tests --------------------------------------------


def test_build_request_create_requires_properties_object() -> None:
    with pytest.raises(ValueError, match="'properties'"):
        build_request("create_contact", {})


def test_build_request_update_requires_contact_id() -> None:
    with pytest.raises(ValueError, match="'contact_id' is required"):
        build_request(
            "update_contact",
            {"properties": {"email": "x"}},
        )


def test_build_request_search_rejects_bad_filter_groups() -> None:
    with pytest.raises(ValueError, match="'filter_groups'"):
        build_request(
            "search_contacts",
            {"filter_groups": "not-a-list"},
        )


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
