"""Unit tests for :class:`DiscordNode`.

Exercises every supported operation against a respx-mocked Discord REST
API. Verifies the ``Authorization: Bot <token>`` prefix is applied.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import DiscordBotCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.discord import DiscordNode
from weftlyflow.nodes.integrations.discord.operations import build_request

_CRED_ID: str = "cr_discord"
_PROJECT_ID: str = "pr_test"


def _resolver(*, bot_token: str = "dsc.abc") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.discord_bot": DiscordBotCredential},
        rows={_CRED_ID: ("weftlyflow.discord_bot", {"bot_token": bot_token}, _PROJECT_ID)},
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


# --- send_message ----------------------------------------------------------


@respx.mock
async def test_send_message_posts_content_with_bot_prefix() -> None:
    route = respx.post("https://discord.com/api/v10/channels/C1/messages").mock(
        return_value=Response(200, json={"id": "m1", "content": "hi"}),
    )
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={
            "operation": "send_message",
            "channel_id": "C1",
            "content": "hi there",
        },
        credentials={"discord_bot": _CRED_ID},
    )
    out = await DiscordNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["id"] == "m1"
    body = json.loads(route.calls.last.request.content)
    assert body == {"content": "hi there"}
    assert route.calls.last.request.headers["authorization"] == "Bot dsc.abc"


@respx.mock
async def test_send_message_with_embeds_only() -> None:
    route = respx.post("https://discord.com/api/v10/channels/C1/messages").mock(
        return_value=Response(200, json={"id": "m1"}),
    )
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={
            "operation": "send_message",
            "channel_id": "C1",
            "embeds": [{"title": "Deploy", "description": "green"}],
            "tts": True,
        },
        credentials={"discord_bot": _CRED_ID},
    )
    await DiscordNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["embeds"][0]["title"] == "Deploy"
    assert body["tts"] is True
    assert "content" not in body


@respx.mock
async def test_send_message_without_body_raises() -> None:
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={"operation": "send_message", "channel_id": "C1"},
        credentials={"discord_bot": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match=r"content.*embeds"):
        await DiscordNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- edit_message / delete_message / get_channel --------------------------


@respx.mock
async def test_edit_message_issues_patch() -> None:
    route = respx.patch(
        "https://discord.com/api/v10/channels/C1/messages/m1",
    ).mock(return_value=Response(200, json={"id": "m1", "content": "edit"}))
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={
            "operation": "edit_message",
            "channel_id": "C1",
            "message_id": "m1",
            "content": "edit",
        },
        credentials={"discord_bot": _CRED_ID},
    )
    await DiscordNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.calls.last.request.method == "PATCH"


@respx.mock
async def test_delete_message_handles_empty_204() -> None:
    route = respx.delete(
        "https://discord.com/api/v10/channels/C1/messages/m1",
    ).mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={
            "operation": "delete_message",
            "channel_id": "C1",
            "message_id": "m1",
        },
        credentials={"discord_bot": _CRED_ID},
    )
    out = await DiscordNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["status"] == 204
    assert result.json["response"] == {}
    assert route.called


@respx.mock
async def test_get_channel_is_a_get() -> None:
    route = respx.get("https://discord.com/api/v10/channels/C1").mock(
        return_value=Response(200, json={"id": "C1", "name": "general"}),
    )
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={"operation": "get_channel", "channel_id": "C1"},
        credentials={"discord_bot": _CRED_ID},
    )
    await DiscordNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- error paths -----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_message() -> None:
    respx.post("https://discord.com/api/v10/channels/C1/messages").mock(
        return_value=Response(403, json={"message": "Missing Access", "code": 50001}),
    )
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={
            "operation": "send_message",
            "channel_id": "C1",
            "content": "hi",
        },
        credentials={"discord_bot": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Missing Access"):
        await DiscordNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={
            "operation": "send_message",
            "channel_id": "C1",
            "content": "hi",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await DiscordNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_bot_token_raises() -> None:
    node = Node(
        id="node_1",
        name="Discord",
        type="weftlyflow.discord",
        parameters={"operation": "get_channel", "channel_id": "C1"},
        credentials={"discord_bot": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'bot_token'"):
        await DiscordNode().execute(
            _ctx_for(node, resolver=_resolver(bot_token="")), [Item()],
        )


# --- direct builder unit tests --------------------------------------------


def test_build_request_send_message_rejects_overlong_content() -> None:
    with pytest.raises(ValueError, match="2000 characters"):
        build_request(
            "send_message",
            {"channel_id": "C1", "content": "x" * 2001},
        )


def test_build_request_edit_message_requires_message_id() -> None:
    with pytest.raises(ValueError, match="message_id"):
        build_request(
            "edit_message",
            {"channel_id": "C1", "content": "x"},
        )


def test_build_request_embeds_must_be_list() -> None:
    with pytest.raises(ValueError, match="embeds"):
        build_request(
            "send_message",
            {"channel_id": "C1", "embeds": "not-a-list"},
        )


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
