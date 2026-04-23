"""Unit tests for :class:`ActiveCampaignNode`.

Exercises every supported operation against a respx-mocked
ActiveCampaign v3 API. Verifies the distinctive raw ``Api-Token``
header (no Bearer prefix), the per-tenant base URL resolution, the
per-resource envelope wrappers (``contact`` / ``contactList`` /
``contactTag``), PUT vs POST, list paging caps, and the
``errors: [{title, detail}]`` envelope parse.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ActiveCampaignApiCredential
from weftlyflow.credentials.types.activecampaign_api import base_url_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.activecampaign import ActiveCampaignNode
from weftlyflow.nodes.integrations.activecampaign.operations import build_request

_CRED_ID: str = "cr_ac"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "ac-secret"
_API_URL: str = "https://acme-55.api-us1.com"
_BASE: str = f"{_API_URL}/api/3"


def _resolver(
    *,
    token: str = _TOKEN,
    api_url: str = _API_URL,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.activecampaign_api": ActiveCampaignApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.activecampaign_api",
                {"api_token": token, "api_url": api_url},
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


# --- list_contacts ---------------------------------------------------


@respx.mock
async def test_list_contacts_sends_raw_api_token() -> None:
    route = respx.get(f"{_BASE}/contacts").mock(
        return_value=Response(200, json={"contacts": []}),
    )
    node = Node(
        id="node_1",
        name="AC",
        type="weftlyflow.activecampaign",
        parameters={
            "operation": "list_contacts",
            "email": "user@example.com",
            "limit": 50,
            "list_id": "7",
        },
        credentials={"activecampaign_api": _CRED_ID},
    )
    await ActiveCampaignNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Api-Token"] == _TOKEN
    assert "Authorization" not in request.headers
    params = request.url.params
    assert params.get("limit") == "50"
    assert params.get("email") == "user@example.com"
    assert params.get("listid") == "7"


def test_list_contacts_caps_limit_at_max() -> None:
    _, _, _, query = build_request("list_contacts", {"limit": 5_000})
    assert query["limit"] == 100


# --- get_contact -----------------------------------------------------


@respx.mock
async def test_get_contact_hits_resource_path() -> None:
    respx.get(f"{_BASE}/contacts/42").mock(
        return_value=Response(200, json={"contact": {"id": "42"}}),
    )
    node = Node(
        id="node_1",
        name="AC",
        type="weftlyflow.activecampaign",
        parameters={"operation": "get_contact", "contact_id": "42"},
        credentials={"activecampaign_api": _CRED_ID},
    )
    await ActiveCampaignNode().execute(_ctx_for(node), [Item()])


# --- create_contact --------------------------------------------------


@respx.mock
async def test_create_contact_wraps_body_in_contact_envelope() -> None:
    route = respx.post(f"{_BASE}/contacts").mock(
        return_value=Response(201, json={"contact": {"id": "new"}}),
    )
    node = Node(
        id="node_1",
        name="AC",
        type="weftlyflow.activecampaign",
        parameters={
            "operation": "create_contact",
            "document": {
                "email": "a@b.com",
                "firstName": "Ada",
                "lastName": "Lovelace",
            },
        },
        credentials={"activecampaign_api": _CRED_ID},
    )
    await ActiveCampaignNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "contact": {
            "email": "a@b.com",
            "firstName": "Ada",
            "lastName": "Lovelace",
        },
    }


def test_create_contact_requires_email() -> None:
    with pytest.raises(ValueError, match=r"'document\.email' is required"):
        build_request("create_contact", {"document": {"firstName": "x"}})


# --- update_contact (PUT) -------------------------------------------


@respx.mock
async def test_update_contact_uses_put_verb() -> None:
    route = respx.put(f"{_BASE}/contacts/42").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="AC",
        type="weftlyflow.activecampaign",
        parameters={
            "operation": "update_contact",
            "contact_id": "42",
            "document": {"firstName": "Grace"},
        },
        credentials={"activecampaign_api": _CRED_ID},
    )
    await ActiveCampaignNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "PUT"


# --- add_contact_to_list --------------------------------------------


@respx.mock
async def test_add_contact_to_list_wraps_contactlist_envelope() -> None:
    route = respx.post(f"{_BASE}/contactLists").mock(
        return_value=Response(201, json={}),
    )
    node = Node(
        id="node_1",
        name="AC",
        type="weftlyflow.activecampaign",
        parameters={
            "operation": "add_contact_to_list",
            "contact_id": "42",
            "list_id": "7",
            "status": 1,
        },
        credentials={"activecampaign_api": _CRED_ID},
    )
    await ActiveCampaignNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "contactList": {"list": "7", "contact": "42", "status": 1},
    }


def test_add_contact_to_list_rejects_bad_status() -> None:
    with pytest.raises(ValueError, match="'status' must be 1"):
        build_request(
            "add_contact_to_list",
            {"contact_id": "1", "list_id": "2", "status": 5},
        )


# --- add_tag_to_contact ---------------------------------------------


@respx.mock
async def test_add_tag_to_contact_wraps_contacttag_envelope() -> None:
    route = respx.post(f"{_BASE}/contactTags").mock(
        return_value=Response(201, json={}),
    )
    node = Node(
        id="node_1",
        name="AC",
        type="weftlyflow.activecampaign",
        parameters={
            "operation": "add_tag_to_contact",
            "contact_id": "42",
            "tag_id": "vip",
        },
        credentials={"activecampaign_api": _CRED_ID},
    )
    await ActiveCampaignNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"contactTag": {"contact": "42", "tag": "vip"}}


# --- base URL normalization -----------------------------------------


def test_base_url_from_adds_scheme_and_prefix() -> None:
    assert base_url_from("acme-55.api-us1.com") == "https://acme-55.api-us1.com/api/3"


def test_base_url_from_preserves_existing_prefix() -> None:
    assert (
        base_url_from("https://acme-55.api-us1.com/api/3/")
        == "https://acme-55.api-us1.com/api/3"
    )


def test_base_url_from_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'api_url' is required"):
        base_url_from("  ")


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_errors_envelope() -> None:
    respx.get(f"{_BASE}/contacts/bad").mock(
        return_value=Response(
            404,
            json={"errors": [{"title": "Not Found", "detail": "No such contact"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="AC",
        type="weftlyflow.activecampaign",
        parameters={"operation": "get_contact", "contact_id": "bad"},
        credentials={"activecampaign_api": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError, match="Not Found: No such contact",
    ):
        await ActiveCampaignNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="AC",
        type="weftlyflow.activecampaign",
        parameters={"operation": "list_contacts"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await ActiveCampaignNode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke_tenant", {})
