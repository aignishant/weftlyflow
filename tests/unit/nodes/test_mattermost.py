"""Unit tests for :class:`MattermostNode`.

Exercises every supported operation against a respx-mocked Mattermost
v4 REST API. Verifies the ``Authorization: Bearer <token>`` header, the
credential-owned base URL (self-hosted pattern — every tenant lives at
its own host), the ``base_url_from`` normalization (with and without
``/api/v4``), and the ``/users/{user}/teams/{team}/channels`` path with
``user_id`` defaulting to ``me``.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import MattermostApiCredential
from weftlyflow.credentials.types.mattermost_api import base_url_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.mattermost import MattermostNode
from weftlyflow.nodes.integrations.mattermost.operations import build_request

_CRED_ID: str = "cr_mm"
_PROJECT_ID: str = "pr_test"
_HOST: str = "https://chat.acme.io"
_BASE: str = f"{_HOST}/api/v4"


def _resolver(
    *,
    access_token: str = "mm-tok",
    base_url: str = _HOST,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.mattermost_api": MattermostApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.mattermost_api",
                {"access_token": access_token, "base_url": base_url},
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


# --- post_message -------------------------------------------------------


@respx.mock
async def test_post_message_uses_bearer_and_body_shape() -> None:
    route = respx.post(f"{_BASE}/posts").mock(
        return_value=Response(201, json={"id": "p1", "message": "hi"}),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={
            "operation": "post_message",
            "channel_id": "c1",
            "message": "hi",
            "root_id": "root-1",
            "props": {"from_bot": True},
            "file_ids": "f1, f2",
        },
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer mm-tok"
    body = json.loads(request.content)
    assert body == {
        "channel_id": "c1",
        "message": "hi",
        "root_id": "root-1",
        "props": {"from_bot": True},
        "file_ids": ["f1", "f2"],
    }


async def test_post_message_requires_message() -> None:
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={
            "operation": "post_message",
            "channel_id": "c1",
            "message": "   ",
        },
        credentials={"mattermost_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'message' is required"):
        await MattermostNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- update_post --------------------------------------------------------


@respx.mock
async def test_update_post_embeds_id_in_body() -> None:
    route = respx.put(f"{_BASE}/posts/p1").mock(
        return_value=Response(200, json={"id": "p1"}),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={
            "operation": "update_post",
            "post_id": "p1",
            "fields": {"message": "edited"},
        },
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"message": "edited", "id": "p1"}


# --- delete_post --------------------------------------------------------


@respx.mock
async def test_delete_post_issues_delete_verb() -> None:
    route = respx.delete(f"{_BASE}/posts/p1").mock(
        return_value=Response(200, json={"status": "OK"}),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={"operation": "delete_post", "post_id": "p1"},
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- get_channel --------------------------------------------------------


@respx.mock
async def test_get_channel_targets_channel_path() -> None:
    route = respx.get(f"{_BASE}/channels/c1").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={"operation": "get_channel", "channel_id": "c1"},
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- list_channels_for_user --------------------------------------------


@respx.mock
async def test_list_channels_defaults_user_id_to_me() -> None:
    route = respx.get(f"{_BASE}/users/me/teams/t1/channels").mock(
        return_value=Response(200, json=[{"id": "c1"}]),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={
            "operation": "list_channels_for_user",
            "team_id": "t1",
        },
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


@respx.mock
async def test_list_channels_honors_explicit_user_id() -> None:
    route = respx.get(f"{_BASE}/users/u1/teams/t1/channels").mock(
        return_value=Response(200, json=[]),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={
            "operation": "list_channels_for_user",
            "user_id": "u1",
            "team_id": "t1",
        },
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- get_user_by_username ----------------------------------------------


@respx.mock
async def test_get_user_by_username_targets_username_path() -> None:
    route = respx.get(f"{_BASE}/users/username/nishant").mock(
        return_value=Response(200, json={"username": "nishant"}),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={
            "operation": "get_user_by_username",
            "username": "nishant",
        },
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- base URL normalization --------------------------------------------


@respx.mock
async def test_base_url_already_ending_with_api_v4_is_reused() -> None:
    route = respx.get(f"{_BASE}/channels/c1").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={"operation": "get_channel", "channel_id": "c1"},
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(
        _ctx_for(node, resolver=_resolver(base_url=f"{_HOST}/api/v4")), [Item()],
    )
    assert route.called


@respx.mock
async def test_base_url_without_scheme_is_https_by_default() -> None:
    route = respx.get(f"{_BASE}/channels/c1").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={"operation": "get_channel", "channel_id": "c1"},
        credentials={"mattermost_api": _CRED_ID},
    )
    await MattermostNode().execute(
        _ctx_for(node, resolver=_resolver(base_url="chat.acme.io")), [Item()],
    )
    assert route.called


def test_base_url_from_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'base_url' is required"):
        base_url_from("   ")


# --- errors / credentials -----------------------------------------------


@respx.mock
async def test_api_error_surfaces_message_and_detailed_error() -> None:
    respx.get(f"{_BASE}/channels/c1").mock(
        return_value=Response(
            403,
            json={"message": "forbidden", "detailed_error": "missing scope"},
        ),
    )
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={"operation": "get_channel", "channel_id": "c1"},
        credentials={"mattermost_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="forbidden: missing scope"):
        await MattermostNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={"operation": "get_channel", "channel_id": "c1"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MattermostNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_empty_base_url_raises() -> None:
    node = Node(
        id="node_1",
        name="Mattermost",
        type="weftlyflow.mattermost",
        parameters={"operation": "get_channel", "channel_id": "c1"},
        credentials={"mattermost_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="base_url"):
        await MattermostNode().execute(
            _ctx_for(node, resolver=_resolver(base_url="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_update_requires_fields() -> None:
    with pytest.raises(ValueError, match="'fields'"):
        build_request("update_post", {"post_id": "p1"})


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_channel", {})
