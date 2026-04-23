"""Unit tests for :class:`GhostNode` and ``GhostAdminCredential``.

Exercises the distinctive per-request HS256 JWT (stdlib only),
``Authorization: Ghost <jwt>`` prefix, resource-envelope body shapes
(``{"posts": [...]}`` / ``{"members": [...]}``) and the optimistic
concurrency requirement on post updates (must echo ``updated_at``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import GhostAdminCredential
from weftlyflow.credentials.types.ghost_admin import build_admin_token
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.ghost import GhostNode
from weftlyflow.nodes.integrations.ghost.operations import build_request

_CRED_ID: str = "cr_ghost"
_PROJECT_ID: str = "pr_test"
_KEY_ID: str = "60f3d3...abcd"
_SECRET_HEX: str = "deadbeef" * 8  # 32-byte secret
_ADMIN_KEY: str = f"{_KEY_ID}:{_SECRET_HEX}"
_BASE: str = "https://demo.ghost.io"


def _resolver(
    *,
    admin_api_key: str = _ADMIN_KEY,
    base_url: str = _BASE,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.ghost_admin": GhostAdminCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.ghost_admin",
                {"base_url": base_url, "admin_api_key": admin_api_key},
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


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * ((4 - len(segment) % 4) % 4)
    return base64.urlsafe_b64decode(segment + padding)


# --- JWT builder ----------------------------------------------------


def test_build_admin_token_has_three_b64url_segments() -> None:
    token = build_admin_token(_ADMIN_KEY, now=1_700_000_000)
    header_seg, claims_seg, signature_seg = token.split(".")
    header = json.loads(_b64url_decode(header_seg))
    claims = json.loads(_b64url_decode(claims_seg))
    assert header == {"alg": "HS256", "typ": "JWT", "kid": _KEY_ID}
    assert claims == {"iat": 1_700_000_000, "exp": 1_700_000_300, "aud": "/admin/"}
    secret_bytes = bytes.fromhex(_SECRET_HEX)
    expected = hmac.new(
        secret_bytes,
        f"{header_seg}.{claims_seg}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    assert _b64url_decode(signature_seg) == expected


def test_build_admin_token_rejects_malformed_key() -> None:
    with pytest.raises(ValueError, match="id:secret_hex"):
        build_admin_token("no-colon-here")


def test_build_admin_token_rejects_non_hex_secret() -> None:
    with pytest.raises(ValueError, match="not valid hex"):
        build_admin_token("abc:zzz")


# --- credential.inject ----------------------------------------------


async def test_credential_inject_sets_ghost_authorization_prefix() -> None:
    request = httpx.Request("GET", f"{_BASE}/ghost/api/admin/posts/")
    out = await GhostAdminCredential().inject({"admin_api_key": _ADMIN_KEY}, request)
    value = out.headers["Authorization"]
    assert value.startswith("Ghost ")
    token = value.removeprefix("Ghost ")
    assert len(token.split(".")) == 3


# --- list_posts -----------------------------------------------------


@respx.mock
async def test_list_posts_forwards_list_query_params() -> None:
    route = respx.get(f"{_BASE}/ghost/api/admin/posts/").mock(
        return_value=Response(200, json={"posts": []}),
    )
    node = Node(
        id="node_1",
        name="Ghost",
        type="weftlyflow.ghost",
        parameters={
            "operation": "list_posts",
            "limit": 5,
            "page": 2,
            "filter": "status:published",
        },
        credentials={"ghost_admin": _CRED_ID},
    )
    await GhostNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["limit"] == "5"
    assert params["page"] == "2"
    assert params["filter"] == "status:published"


# --- get_post -------------------------------------------------------


@respx.mock
async def test_get_post_percent_encodes_post_id() -> None:
    route = respx.get(f"{_BASE}/ghost/api/admin/posts/abc%20123/").mock(
        return_value=Response(200, json={"posts": [{"id": "abc 123"}]}),
    )
    node = Node(
        id="node_1",
        name="Ghost",
        type="weftlyflow.ghost",
        parameters={"operation": "get_post", "post_id": "abc 123"},
        credentials={"ghost_admin": _CRED_ID},
    )
    await GhostNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- create_post ----------------------------------------------------


@respx.mock
async def test_create_post_wraps_body_in_posts_envelope() -> None:
    route = respx.post(f"{_BASE}/ghost/api/admin/posts/").mock(
        return_value=Response(201, json={"posts": [{"id": "p1"}]}),
    )
    node = Node(
        id="node_1",
        name="Ghost",
        type="weftlyflow.ghost",
        parameters={
            "operation": "create_post",
            "title": "Hello",
            "html": "<p>world</p>",
            "status": "draft",
            "tags": ["news"],
        },
        credentials={"ghost_admin": _CRED_ID},
    )
    await GhostNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "posts": [
            {
                "title": "Hello",
                "html": "<p>world</p>",
                "status": "draft",
                "tags": ["news"],
            },
        ],
    }


def test_create_post_requires_title() -> None:
    with pytest.raises(ValueError, match="'title' is required"):
        build_request("create_post", {})


# --- update_post ----------------------------------------------------


@respx.mock
async def test_update_post_echoes_updated_at() -> None:
    route = respx.put(f"{_BASE}/ghost/api/admin/posts/p1/").mock(
        return_value=Response(200, json={"posts": [{"id": "p1"}]}),
    )
    node = Node(
        id="node_1",
        name="Ghost",
        type="weftlyflow.ghost",
        parameters={
            "operation": "update_post",
            "post_id": "p1",
            "updated_at": "2026-04-01T00:00:00.000Z",
            "html": "<p>new</p>",
        },
        credentials={"ghost_admin": _CRED_ID},
    )
    await GhostNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["posts"][0]["updated_at"] == "2026-04-01T00:00:00.000Z"
    assert body["posts"][0]["html"] == "<p>new</p>"


def test_update_post_requires_updated_at() -> None:
    with pytest.raises(ValueError, match="optimistic concurrency"):
        build_request("update_post", {"post_id": "p1"})


def test_update_post_requires_a_field_to_change() -> None:
    with pytest.raises(ValueError, match="at least one field"):
        build_request(
            "update_post",
            {"post_id": "p1", "updated_at": "2026-04-01T00:00:00.000Z"},
        )


# --- delete_post ----------------------------------------------------


@respx.mock
async def test_delete_post_uses_delete_verb() -> None:
    route = respx.delete(f"{_BASE}/ghost/api/admin/posts/p1/").mock(
        return_value=Response(204),
    )
    node = Node(
        id="node_1",
        name="Ghost",
        type="weftlyflow.ghost",
        parameters={"operation": "delete_post", "post_id": "p1"},
        credentials={"ghost_admin": _CRED_ID},
    )
    await GhostNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- members --------------------------------------------------------


@respx.mock
async def test_create_member_uses_members_envelope() -> None:
    route = respx.post(f"{_BASE}/ghost/api/admin/members/").mock(
        return_value=Response(201, json={"members": [{"id": "m1"}]}),
    )
    node = Node(
        id="node_1",
        name="Ghost",
        type="weftlyflow.ghost",
        parameters={
            "operation": "create_member",
            "email": "a@b.c",
            "name": "A",
            "labels": ["vip"],
        },
        credentials={"ghost_admin": _CRED_ID},
    )
    await GhostNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"members": [{"email": "a@b.c", "name": "A", "labels": ["vip"]}]}


# --- errors ---------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed_from_errors_array() -> None:
    respx.post(f"{_BASE}/ghost/api/admin/posts/").mock(
        return_value=Response(
            422,
            json={"errors": [{"message": "Validation failed", "context": "title"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Ghost",
        type="weftlyflow.ghost",
        parameters={"operation": "create_post", "title": "X"},
        credentials={"ghost_admin": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Validation failed"):
        await GhostNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Ghost",
        type="weftlyflow.ghost",
        parameters={"operation": "list_posts"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await GhostNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
