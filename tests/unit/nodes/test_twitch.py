"""Unit tests for :class:`TwitchNode`.

Exercises every supported Helix read operation against a respx-mocked
Twitch API. Verifies the distinctive dual-header auth shape
(``Authorization: Bearer`` *and* ``Client-Id``) enforced on every call,
the repeated-query-parameter serialization used for Helix list filters,
and the ``error: message`` envelope parse.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import TwitchApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.twitch import TwitchNode
from weftlyflow.nodes.integrations.twitch.operations import build_request

_CRED_ID: str = "cr_tw"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "oauth-token"
_CLIENT_ID: str = "client-id-abc"
_BASE: str = "https://api.twitch.tv/helix"


def _resolver(
    *,
    token: str = _TOKEN,
    client_id: str = _CLIENT_ID,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.twitch_api": TwitchApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.twitch_api",
                {"access_token": token, "client_id": client_id},
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


# --- get_users -------------------------------------------------------


@respx.mock
async def test_get_users_sends_bearer_and_client_id_headers() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json={"data": [{"id": "1"}]}),
    )
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={"operation": "get_users", "logins": "ninja,shroud"},
        credentials={"twitch_api": _CRED_ID},
    )
    await TwitchNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.headers["Client-Id"] == _CLIENT_ID
    url = str(request.url)
    assert "login=ninja" in url
    assert "login=shroud" in url


@respx.mock
async def test_get_users_accepts_user_ids() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={"operation": "get_users", "user_ids": "42,1337"},
        credentials={"twitch_api": _CRED_ID},
    )
    await TwitchNode().execute(_ctx_for(node), [Item()])
    url = str(route.calls.last.request.url)
    assert "id=42" in url
    assert "id=1337" in url


def test_get_users_rejects_missing_filters() -> None:
    with pytest.raises(ValueError, match="at least one of"):
        build_request("get_users", {})


# --- get_channel -----------------------------------------------------


@respx.mock
async def test_get_channel_sends_broadcaster_id() -> None:
    route = respx.get(f"{_BASE}/channels").mock(
        return_value=Response(200, json={"data": [{"broadcaster_id": "99"}]}),
    )
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={"operation": "get_channel", "broadcaster_id": "99"},
        credentials={"twitch_api": _CRED_ID},
    )
    await TwitchNode().execute(_ctx_for(node), [Item()])
    assert "broadcaster_id=99" in str(route.calls.last.request.url)


def test_get_channel_requires_broadcaster() -> None:
    with pytest.raises(ValueError, match="'broadcaster_id' is required"):
        build_request("get_channel", {})


# --- get_streams -----------------------------------------------------


@respx.mock
async def test_get_streams_filters_by_language_and_user() -> None:
    route = respx.get(f"{_BASE}/streams").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={
            "operation": "get_streams",
            "user_logins": "alice,bob",
            "language": "en",
            "first": 50,
        },
        credentials={"twitch_api": _CRED_ID},
    )
    await TwitchNode().execute(_ctx_for(node), [Item()])
    url = str(route.calls.last.request.url)
    assert "user_login=alice" in url
    assert "user_login=bob" in url
    assert "language=en" in url
    assert "first=50" in url


# --- get_videos ------------------------------------------------------


@respx.mock
async def test_get_videos_with_user_id() -> None:
    route = respx.get(f"{_BASE}/videos").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={"operation": "get_videos", "user_id": "42"},
        credentials={"twitch_api": _CRED_ID},
    )
    await TwitchNode().execute(_ctx_for(node), [Item()])
    assert "user_id=42" in str(route.calls.last.request.url)


def test_get_videos_requires_filter() -> None:
    with pytest.raises(ValueError, match="requires one of"):
        build_request("get_videos", {})


# --- get_followers ---------------------------------------------------


@respx.mock
async def test_get_followers_hits_channels_followers_endpoint() -> None:
    route = respx.get(f"{_BASE}/channels/followers").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={
            "operation": "get_followers",
            "broadcaster_id": "99",
            "after": "cursor-xyz",
        },
        credentials={"twitch_api": _CRED_ID},
    )
    await TwitchNode().execute(_ctx_for(node), [Item()])
    url = str(route.calls.last.request.url)
    assert "broadcaster_id=99" in url
    assert "after=cursor-xyz" in url


# --- search_channels -------------------------------------------------


@respx.mock
async def test_search_channels_live_only_coerced_to_lowercase_string() -> None:
    route = respx.get(f"{_BASE}/search/channels").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={
            "operation": "search_channels",
            "query": "python",
            "live_only": True,
        },
        credentials={"twitch_api": _CRED_ID},
    )
    await TwitchNode().execute(_ctx_for(node), [Item()])
    url = str(route.calls.last.request.url)
    assert "query=python" in url
    assert "live_only=true" in url


# --- errors / credentials --------------------------------------------


@respx.mock
async def test_api_error_surfaces_error_and_message() -> None:
    respx.get(f"{_BASE}/users").mock(
        return_value=Response(
            401,
            json={"error": "Unauthorized", "message": "Invalid OAuth token"},
        ),
    )
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={"operation": "get_users", "logins": "x"},
        credentials={"twitch_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Unauthorized: Invalid OAuth token"):
        await TwitchNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={"operation": "get_users", "logins": "x"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await TwitchNode().execute(_ctx_for(node), [Item()])


async def test_missing_client_id_raises() -> None:
    node = Node(
        id="node_1",
        name="Twitch",
        type="weftlyflow.twitch",
        parameters={"operation": "get_users", "logins": "x"},
        credentials={"twitch_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'client_id'"):
        await TwitchNode().execute(
            _ctx_for(node, resolver=_resolver(client_id="")),
            [Item()],
        )


# --- direct builder unit tests ---------------------------------------


def test_build_caps_page_size_at_max() -> None:
    _, query = build_request(
        "get_streams",
        {"user_ids": "1", "first": 999_999},
    )
    assert query["first"] == 100


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("ban_everyone", {})
