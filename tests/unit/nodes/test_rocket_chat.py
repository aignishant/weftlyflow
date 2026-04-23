"""Unit tests for :class:`RocketChatNode` and ``RocketChatApiCredential``.

Exercises the distinctive ``X-Auth-Token`` + ``X-User-Id`` dual-header
auth pair (both mandatory), self-hosted ``base_url`` routing, chat.post
``roomId``/``text`` body shape, and the ``{"success": false}`` error
envelope.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import RocketChatApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.rocket_chat import RocketChatNode
from weftlyflow.nodes.integrations.rocket_chat.operations import build_request

_CRED_ID: str = "cr_rocket"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "rctoken-abc"
_USER_ID: str = "u123"
_BASE: str = "https://chat.example.com"


def _resolver(
    *,
    auth_token: str = _TOKEN,
    user_id: str = _USER_ID,
    base_url: str = _BASE,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.rocket_chat_api": RocketChatApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.rocket_chat_api",
                {
                    "base_url": base_url,
                    "user_id": user_id,
                    "auth_token": auth_token,
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


# --- credential.inject ----------------------------------------------


async def test_credential_inject_sets_dual_auth_headers() -> None:
    request = httpx.Request("GET", f"{_BASE}/api/v1/me")
    out = await RocketChatApiCredential().inject(
        {"auth_token": _TOKEN, "user_id": _USER_ID},
        request,
    )
    assert out.headers["X-Auth-Token"] == _TOKEN
    assert out.headers["X-User-Id"] == _USER_ID
    assert "Authorization" not in out.headers


# --- post_message ----------------------------------------------------


@respx.mock
async def test_post_message_sends_room_id_and_text_in_body() -> None:
    route = respx.post(f"{_BASE}/api/v1/chat.postMessage").mock(
        return_value=Response(200, json={"success": True, "message": {"_id": "m1"}}),
    )
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={
            "operation": "post_message",
            "room_id": "GENERAL",
            "text": "Hello, world",
            "alias": "bot",
            "emoji": ":robot:",
        },
        credentials={"rocket_chat_api": _CRED_ID},
    )
    await RocketChatNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["X-Auth-Token"] == _TOKEN
    assert request.headers["X-User-Id"] == _USER_ID
    body = json.loads(request.content)
    assert body == {
        "roomId": "GENERAL",
        "text": "Hello, world",
        "alias": "bot",
        "emoji": ":robot:",
    }


def test_post_message_requires_room_and_text() -> None:
    with pytest.raises(ValueError, match="'room_id' is required"):
        build_request("post_message", {})
    with pytest.raises(ValueError, match="'text' is required"):
        build_request("post_message", {"room_id": "r"})


# --- update/delete ---------------------------------------------------


@respx.mock
async def test_update_message_sends_msg_id_in_body() -> None:
    route = respx.post(f"{_BASE}/api/v1/chat.update").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={
            "operation": "update_message",
            "room_id": "GENERAL",
            "message_id": "m1",
            "text": "edited",
        },
        credentials={"rocket_chat_api": _CRED_ID},
    )
    await RocketChatNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"roomId": "GENERAL", "msgId": "m1", "text": "edited"}


@respx.mock
async def test_delete_message_optionally_includes_as_user() -> None:
    route = respx.post(f"{_BASE}/api/v1/chat.delete").mock(
        return_value=Response(200, json={"success": True}),
    )
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={
            "operation": "delete_message",
            "room_id": "GENERAL",
            "message_id": "m1",
            "as_user": True,
        },
        credentials={"rocket_chat_api": _CRED_ID},
    )
    await RocketChatNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"roomId": "GENERAL", "msgId": "m1", "asUser": True}


# --- channels --------------------------------------------------------


@respx.mock
async def test_list_channels_sends_camelcase_query() -> None:
    route = respx.get(f"{_BASE}/api/v1/channels.list").mock(
        return_value=Response(200, json={"channels": [], "success": True}),
    )
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={"operation": "list_channels", "count": 25, "offset": 0},
        credentials={"rocket_chat_api": _CRED_ID},
    )
    await RocketChatNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["count"] == "25"
    assert params["offset"] == "0"


@respx.mock
async def test_create_channel_sends_members_and_readonly() -> None:
    route = respx.post(f"{_BASE}/api/v1/channels.create").mock(
        return_value=Response(200, json={"success": True, "channel": {"_id": "c1"}}),
    )
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={
            "operation": "create_channel",
            "name": "my-channel",
            "members": ["alice", "bob"],
            "read_only": True,
        },
        credentials={"rocket_chat_api": _CRED_ID},
    )
    await RocketChatNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "name": "my-channel",
        "members": ["alice", "bob"],
        "readOnly": True,
    }


# --- users -----------------------------------------------------------


@respx.mock
async def test_get_user_by_username_uses_query() -> None:
    route = respx.get(f"{_BASE}/api/v1/users.info").mock(
        return_value=Response(200, json={"success": True, "user": {"_id": "u1"}}),
    )
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={"operation": "get_user", "username": "alice"},
        credentials={"rocket_chat_api": _CRED_ID},
    )
    await RocketChatNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["username"] == "alice"


def test_get_user_requires_id_or_username() -> None:
    with pytest.raises(ValueError, match="'user_id' or 'username' is required"):
        build_request("get_user", {})


# --- errors ----------------------------------------------------------


@respx.mock
async def test_success_false_envelope_raises_even_on_http_200() -> None:
    respx.post(f"{_BASE}/api/v1/chat.postMessage").mock(
        return_value=Response(
            200,
            json={"success": False, "error": "room not found"},
        ),
    )
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={
            "operation": "post_message",
            "room_id": "missing",
            "text": "x",
        },
        credentials={"rocket_chat_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="room not found"):
        await RocketChatNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_http_error_envelope_is_parsed() -> None:
    respx.post(f"{_BASE}/api/v1/chat.postMessage").mock(
        return_value=Response(401, json={"message": "unauthorized"}),
    )
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={
            "operation": "post_message",
            "room_id": "r",
            "text": "x",
        },
        credentials={"rocket_chat_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unauthorized"):
        await RocketChatNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={"operation": "list_channels"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await RocketChatNode().execute(_ctx_for(node), [Item()])


async def test_missing_user_id_in_credential_raises() -> None:
    resolver = _resolver(user_id="")
    node = Node(
        id="node_1",
        name="Rocket.Chat",
        type="weftlyflow.rocket_chat",
        parameters={"operation": "list_channels"},
        credentials={"rocket_chat_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'user_id'"):
        await RocketChatNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
