"""Unit tests for :class:`FacebookGraphNode` and ``FacebookGraphCredential``.

Exercises the version-prefixed ``/v21.0`` host, generic node/edge
dispatcher, and the distinctive HMAC-SHA256 ``appsecret_proof`` query
parameter that gets appended whenever an ``app_secret`` is configured.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import FacebookGraphCredential
from weftlyflow.credentials.types.facebook_graph import build_appsecret_proof
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.facebook import FacebookGraphNode
from weftlyflow.nodes.integrations.facebook.operations import build_request

_CRED_ID: str = "cr_fb"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "EAAFB-access-token"
_APP_SECRET: str = "shhh-app-secret"
_VERSION: str = "v21.0"
_BASE: str = f"https://graph.facebook.com/{_VERSION}"


def _resolver(
    *,
    token: str = _TOKEN,
    app_secret: str = "",
    api_version: str = _VERSION,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.facebook_graph": FacebookGraphCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.facebook_graph",
                {
                    "access_token": token,
                    "app_secret": app_secret,
                    "api_version": api_version,
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


# --- build_appsecret_proof ------------------------------------------


def test_appsecret_proof_matches_hmac_sha256_hex() -> None:
    expected = hmac.new(
        _APP_SECRET.encode("utf-8"),
        _TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert build_appsecret_proof(_TOKEN, _APP_SECRET) == expected


def test_appsecret_proof_requires_both_inputs() -> None:
    with pytest.raises(ValueError, match="both access_token and app_secret"):
        build_appsecret_proof("", "secret")
    with pytest.raises(ValueError, match="both access_token and app_secret"):
        build_appsecret_proof("token", "")


# --- credential.inject ----------------------------------------------


async def test_credential_inject_sets_bearer_only_without_app_secret() -> None:
    request = httpx.Request("GET", "https://graph.facebook.com/v21.0/me")
    out = await FacebookGraphCredential().inject({"access_token": _TOKEN}, request)
    assert out.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert "appsecret_proof" not in str(out.url)


async def test_credential_inject_appends_appsecret_proof_query() -> None:
    request = httpx.Request("GET", "https://graph.facebook.com/v21.0/me")
    out = await FacebookGraphCredential().inject(
        {"access_token": _TOKEN, "app_secret": _APP_SECRET},
        request,
    )
    expected_proof = build_appsecret_proof(_TOKEN, _APP_SECRET)
    assert out.url.params.get("appsecret_proof") == expected_proof


# --- get_me ----------------------------------------------------------


@respx.mock
async def test_get_me_sets_bearer_token() -> None:
    route = respx.get(f"{_BASE}/me").mock(
        return_value=Response(200, json={"id": "100"}),
    )
    node = Node(
        id="node_1",
        name="FB",
        type="weftlyflow.facebook_graph",
        parameters={"operation": "get_me", "fields": "id,name"},
        credentials={"facebook_graph": _CRED_ID},
    )
    await FacebookGraphNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.url.params.get("fields") == "id,name"


@respx.mock
async def test_get_me_appends_appsecret_proof_when_app_secret_set() -> None:
    route = respx.get(f"{_BASE}/me").mock(
        return_value=Response(200, json={"id": "100"}),
    )
    node = Node(
        id="node_1",
        name="FB",
        type="weftlyflow.facebook_graph",
        parameters={"operation": "get_me"},
        credentials={"facebook_graph": _CRED_ID},
    )
    ctx = _ctx_for(node, resolver=_resolver(app_secret=_APP_SECRET))
    await FacebookGraphNode().execute(ctx, [Item()])
    proof = route.calls.last.request.url.params.get("appsecret_proof")
    assert proof == build_appsecret_proof(_TOKEN, _APP_SECRET)


# --- get_node / list_edge / create_edge / delete_node ---------------


@respx.mock
async def test_get_node_uses_node_id_in_path() -> None:
    respx.get(f"{_BASE}/12345").mock(return_value=Response(200, json={"id": "12345"}))
    node = Node(
        id="node_1",
        name="FB",
        type="weftlyflow.facebook_graph",
        parameters={"operation": "get_node", "node_id": "12345"},
        credentials={"facebook_graph": _CRED_ID},
    )
    await FacebookGraphNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_list_edge_passes_pagination_cursors() -> None:
    route = respx.get(f"{_BASE}/PAGE-1/posts").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="FB",
        type="weftlyflow.facebook_graph",
        parameters={
            "operation": "list_edge",
            "node_id": "PAGE-1",
            "edge": "posts",
            "limit": 25,
            "after": "abc-cursor",
            "fields": "id,message",
        },
        credentials={"facebook_graph": _CRED_ID},
    )
    await FacebookGraphNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("limit") == "25"
    assert params.get("after") == "abc-cursor"
    assert params.get("fields") == "id,message"


@respx.mock
async def test_create_edge_posts_json_body() -> None:
    route = respx.post(f"{_BASE}/PAGE-1/feed").mock(
        return_value=Response(200, json={"id": "POST-1"}),
    )
    node = Node(
        id="node_1",
        name="FB",
        type="weftlyflow.facebook_graph",
        parameters={
            "operation": "create_edge",
            "node_id": "PAGE-1",
            "edge": "feed",
            "body": {"message": "Hello, Graph!"},
        },
        credentials={"facebook_graph": _CRED_ID},
    )
    await FacebookGraphNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"message": "Hello, Graph!"}


@respx.mock
async def test_delete_node_uses_delete_method() -> None:
    route = respx.delete(f"{_BASE}/POST-1").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="FB",
        type="weftlyflow.facebook_graph",
        parameters={"operation": "delete_node", "node_id": "POST-1"},
        credentials={"facebook_graph": _CRED_ID},
    )
    await FacebookGraphNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "DELETE"


# --- builder validation ---------------------------------------------


def test_get_node_requires_node_id() -> None:
    with pytest.raises(ValueError, match="'node_id' is required"):
        build_request("get_node", {})


def test_list_edge_requires_node_id_and_edge() -> None:
    with pytest.raises(ValueError, match="'node_id' is required"):
        build_request("list_edge", {})
    with pytest.raises(ValueError, match="'edge' is required"):
        build_request("list_edge", {"node_id": "x"})


def test_create_edge_requires_body() -> None:
    with pytest.raises(ValueError, match="'body' is required"):
        build_request(
            "create_edge",
            {"node_id": "x", "edge": "feed"},
        )


def test_create_edge_rejects_non_dict_body() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        build_request(
            "create_edge",
            {"node_id": "x", "edge": "feed", "body": "nope"},
        )


# --- errors ----------------------------------------------------------


@respx.mock
async def test_error_envelope_is_parsed() -> None:
    respx.get(f"{_BASE}/me").mock(
        return_value=Response(
            400,
            json={
                "error": {
                    "message": "Invalid OAuth access token.",
                    "code": 190,
                },
            },
        ),
    )
    node = Node(
        id="node_1",
        name="FB",
        type="weftlyflow.facebook_graph",
        parameters={"operation": "get_me"},
        credentials={"facebook_graph": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Invalid OAuth access token"):
        await FacebookGraphNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="FB",
        type="weftlyflow.facebook_graph",
        parameters={"operation": "get_me"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await FacebookGraphNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
