"""Unit tests for :class:`OktaNode`.

Exercises every supported operation against a respx-mocked Okta v1 API.
Verifies the distinctive ``Authorization: SSWS <token>`` custom scheme
(not Bearer, not Basic), the credential-owned per-org base URL, the
nested ``profile`` body shape on create/update, the ``activate`` query
flag defaulting to ``true``, the lifecycle-transition POST path for
deactivate, and the ``errorSummary: errorCauses[0].errorSummary``
error-envelope parse.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import OktaApiCredential
from weftlyflow.credentials.types.okta_api import base_url_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.okta import OktaNode
from weftlyflow.nodes.integrations.okta.operations import build_request

_CRED_ID: str = "cr_okta"
_PROJECT_ID: str = "pr_test"
_ORG_URL: str = "https://acme.okta.com"
_TOKEN: str = "okta-secret"
_BASE: str = f"{_ORG_URL}/api/v1"


def _resolver(
    *,
    token: str = _TOKEN,
    org_url: str = _ORG_URL,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.okta_api": OktaApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.okta_api",
                {"api_token": token, "org_url": org_url},
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


# --- list_users --------------------------------------------------------


@respx.mock
async def test_list_users_sends_ssws_header_not_bearer() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json=[{"id": "u1"}]),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={
            "operation": "list_users",
            "search": 'profile.email eq "a@x.io"',
            "limit": 10,
        },
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"SSWS {_TOKEN}"
    assert "Bearer" not in request.headers["Authorization"]
    url = str(request.url)
    assert "limit=10" in url
    assert "search=" in url


@respx.mock
async def test_list_users_paginates_with_after_cursor() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json=[]),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={
            "operation": "list_users",
            "after": "opaque-cursor-abc",
        },
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert "after=opaque-cursor-abc" in str(route.calls.last.request.url)


# --- get_user ----------------------------------------------------------


@respx.mock
async def test_get_user_targets_user_path() -> None:
    route = respx.get(f"{_BASE}/users/00u1").mock(
        return_value=Response(200, json={"id": "00u1"}),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={"operation": "get_user", "user_id": "00u1"},
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- create_user -------------------------------------------------------


@respx.mock
async def test_create_user_nests_profile_and_activates_by_default() -> None:
    route = respx.post(f"{_BASE}/users").mock(
        return_value=Response(200, json={"id": "00u2"}),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={
            "operation": "create_user",
            "profile": {
                "firstName": "Ada",
                "lastName": "Lovelace",
                "email": "ada@example.com",
                "login": "ada@example.com",
            },
            "password": "s3cret",
            "group_ids": "grp_a, grp_b",
        },
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert "activate=true" in str(request.url)
    body = json.loads(request.content)
    assert body["profile"]["email"] == "ada@example.com"
    assert body["credentials"] == {"password": {"value": "s3cret"}}
    assert body["groupIds"] == ["grp_a", "grp_b"]


def test_create_user_rejects_missing_required_profile_fields() -> None:
    with pytest.raises(ValueError, match="missing required field"):
        build_request(
            "create_user",
            {"profile": {"firstName": "Ada"}},
        )


@respx.mock
async def test_create_user_respects_activate_false() -> None:
    route = respx.post(f"{_BASE}/users").mock(
        return_value=Response(200, json={"id": "00u3"}),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={
            "operation": "create_user",
            "activate": False,
            "profile": {
                "firstName": "Stage",
                "lastName": "User",
                "email": "stage@example.com",
                "login": "stage@example.com",
            },
        },
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert "activate=false" in str(route.calls.last.request.url)


# --- update_user -------------------------------------------------------


@respx.mock
async def test_update_user_posts_nested_profile_patch() -> None:
    route = respx.post(f"{_BASE}/users/00u1").mock(
        return_value=Response(200, json={"id": "00u1"}),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={
            "operation": "update_user",
            "user_id": "00u1",
            "profile": {"title": "Staff Engineer", "department": "Platform"},
        },
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"profile": {"title": "Staff Engineer", "department": "Platform"}}


def test_update_user_rejects_unknown_profile_field() -> None:
    with pytest.raises(ValueError, match="unknown profile field"):
        build_request(
            "update_user",
            {"user_id": "00u1", "profile": {"bogus": 1}},
        )


# --- deactivate_user ---------------------------------------------------


@respx.mock
async def test_deactivate_user_hits_lifecycle_subresource() -> None:
    route = respx.post(f"{_BASE}/users/00u1/lifecycle/deactivate").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={
            "operation": "deactivate_user",
            "user_id": "00u1",
            "send_email": False,
        },
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert "sendEmail=false" in str(route.calls.last.request.url)


# --- list_groups -------------------------------------------------------


@respx.mock
async def test_list_groups_accepts_q_prefix_search() -> None:
    route = respx.get(f"{_BASE}/groups").mock(
        return_value=Response(200, json=[]),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={"operation": "list_groups", "q": "eng"},
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert "q=eng" in str(route.calls.last.request.url)


# --- org URL normalization ---------------------------------------------


@respx.mock
async def test_org_url_without_scheme_gets_https() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json=[]),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={"operation": "list_users"},
        credentials={"okta_api": _CRED_ID},
    )
    await OktaNode().execute(
        _ctx_for(node, resolver=_resolver(org_url="acme.okta.com")), [Item()],
    )
    assert route.called


def test_base_url_from_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'org_url' is required"):
        base_url_from("   ")


# --- errors / credentials ----------------------------------------------


@respx.mock
async def test_api_error_surfaces_summary_and_cause() -> None:
    respx.get(f"{_BASE}/users").mock(
        return_value=Response(
            400,
            json={
                "errorSummary": "Api validation failed",
                "errorCauses": [{"errorSummary": "login: already exists"}],
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={"operation": "list_users"},
        credentials={"okta_api": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError, match="Api validation failed: login: already exists",
    ):
        await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Okta",
        type="weftlyflow.okta",
        parameters={"operation": "list_users"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await OktaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- direct builder unit tests -----------------------------------------


def test_build_list_caps_limit_at_max() -> None:
    _, _, _, query = build_request("list_users", {"limit": 9_999})
    assert query["limit"] == 200


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("erase_all_data", {})
