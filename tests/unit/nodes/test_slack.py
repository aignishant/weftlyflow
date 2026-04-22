"""Unit tests for :class:`SlackNode`.

Exercises every supported operation against a respx-mocked Slack Web API so
no network is required. Each test covers a specific behaviour (one per
test function, per AAA) and checks the outbound request body as well as
the emitted item shape.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import SlackApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.slack import SlackNode
from weftlyflow.nodes.integrations.slack.operations import build_request

_CRED_ID: str = "cr_slack"
_PROJECT_ID: str = "pr_test"


def _resolver(
    *,
    access_token: str = "xoxb-123",
    default_channel: str = "",
) -> InMemoryCredentialResolver:
    payload: dict[str, object] = {"access_token": access_token}
    if default_channel:
        payload["default_channel"] = default_channel
    return InMemoryCredentialResolver(
        types={"weftlyflow.slack_api": SlackApiCredential},
        rows={_CRED_ID: ("weftlyflow.slack_api", payload, _PROJECT_ID)},
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


# --- post_message -----------------------------------------------------------


@respx.mock
async def test_post_message_sends_channel_and_text() -> None:
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(
            200,
            json={"ok": True, "channel": "C1", "ts": "1700000000.000100"},
        ),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={
            "operation": "post_message",
            "channel": "#general",
            "text": "hello world",
        },
        credentials={"slack_api": _CRED_ID},
    )
    out = await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["ok"] is True
    assert result.json["operation"] == "post_message"
    assert result.json["response"]["ts"] == "1700000000.000100"

    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body == {"channel": "#general", "text": "hello world"}
    assert route.calls.last.request.headers["authorization"] == "Bearer xoxb-123"


@respx.mock
async def test_post_message_resolves_expression_per_item() -> None:
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(200, json={"ok": True}),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={
            "operation": "post_message",
            "channel": "#alerts",
            "text": "hello {{ $json.name }}",
        },
        credentials={"slack_api": _CRED_ID},
    )
    inputs = [Item(json={"name": "Ada"}), Item(json={"name": "Grace"})]
    out = await SlackNode().execute(
        _ctx_for(node, inputs=inputs, resolver=_resolver()), inputs,
    )
    texts = [json.loads(call.request.content)["text"] for call in route.calls]
    assert texts == ["hello Ada", "hello Grace"]
    assert len(out[0]) == 2


@respx.mock
async def test_post_message_falls_back_to_default_channel() -> None:
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(200, json={"ok": True}),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "post_message", "text": "ping"},
        credentials={"slack_api": _CRED_ID},
    )
    resolver = _resolver(default_channel="C9999")
    await SlackNode().execute(_ctx_for(node, resolver=resolver), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["channel"] == "C9999"


@respx.mock
async def test_post_message_without_channel_raises() -> None:
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "post_message", "text": "oops"},
        credentials={"slack_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="channel"):
        await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_post_message_with_blocks_sends_list() -> None:
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(200, json={"ok": True}),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={
            "operation": "post_message",
            "channel": "C1",
            "text": "fallback",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}],
            "thread_ts": "1700000000.000100",
            "as_markdown": False,
            "unfurl_links": False,
        },
        credentials={"slack_api": _CRED_ID},
    )
    await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["blocks"][0]["type"] == "section"
    assert body["thread_ts"] == "1700000000.000100"
    assert body["mrkdwn"] is False
    assert body["unfurl_links"] is False


# --- update_message / delete_message ---------------------------------------


@respx.mock
async def test_update_message_requires_ts() -> None:
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "update_message", "channel": "C1", "text": "edit"},
        credentials={"slack_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="ts"):
        await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_update_message_posts_channel_ts_text() -> None:
    route = respx.post("https://slack.com/api/chat.update").mock(
        return_value=Response(200, json={"ok": True, "ts": "1700000000.000100"}),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={
            "operation": "update_message",
            "channel": "C1",
            "ts": "1700000000.000100",
            "text": "edited",
        },
        credentials={"slack_api": _CRED_ID},
    )
    await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "channel": "C1",
        "ts": "1700000000.000100",
        "text": "edited",
    }


@respx.mock
async def test_delete_message_posts_channel_and_ts() -> None:
    route = respx.post("https://slack.com/api/chat.delete").mock(
        return_value=Response(200, json={"ok": True}),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={
            "operation": "delete_message",
            "channel": "C1",
            "ts": "1700000000.000100",
        },
        credentials={"slack_api": _CRED_ID},
    )
    await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"channel": "C1", "ts": "1700000000.000100"}


# --- list_channels ---------------------------------------------------------


@respx.mock
async def test_get_channel_history_emits_messages_list() -> None:
    route = respx.post("https://slack.com/api/conversations.history").mock(
        return_value=Response(
            200,
            json={
                "ok": True,
                "messages": [{"ts": "1.1", "text": "hi"}, {"ts": "1.2", "text": "bye"}],
                "has_more": False,
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={
            "operation": "get_channel_history",
            "channel": "C1",
            "limit": 25,
            "oldest": "1.0",
            "inclusive": True,
        },
        credentials={"slack_api": _CRED_ID},
    )
    out = await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [m["text"] for m in result.json["messages"]] == ["hi", "bye"]
    body = json.loads(route.calls.last.request.content)
    assert body == {"channel": "C1", "limit": 25, "oldest": "1.0", "inclusive": True}


@respx.mock
async def test_add_reaction_posts_name_and_timestamp() -> None:
    route = respx.post("https://slack.com/api/reactions.add").mock(
        return_value=Response(200, json={"ok": True}),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={
            "operation": "add_reaction",
            "channel": "C1",
            "ts": "1700000000.000100",
            "emoji": ":thumbsup:",
        },
        credentials={"slack_api": _CRED_ID},
    )
    await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "channel": "C1",
        "timestamp": "1700000000.000100",
        "name": "thumbsup",
    }


@respx.mock
async def test_add_reaction_requires_ts() -> None:
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "add_reaction", "channel": "C1", "emoji": "eyes"},
        credentials={"slack_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="ts"):
        await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_list_users_emits_members_list() -> None:
    route = respx.post("https://slack.com/api/users.list").mock(
        return_value=Response(
            200,
            json={
                "ok": True,
                "members": [{"id": "U1", "name": "ada"}, {"id": "U2", "name": "grace"}],
                "response_metadata": {"next_cursor": ""},
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "list_users", "limit": 50, "include_locale": True},
        credentials={"slack_api": _CRED_ID},
    )
    out = await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [m["name"] for m in result.json["members"]] == ["ada", "grace"]
    body = json.loads(route.calls.last.request.content)
    assert body == {"limit": 50, "include_locale": True}


@respx.mock
async def test_slack_oauth2_credential_injects_same_header() -> None:
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(200, json={"ok": True}),
    )
    from weftlyflow.credentials.types import SlackOAuth2Credential

    resolver = InMemoryCredentialResolver(
        types={"weftlyflow.slack_oauth2": SlackOAuth2Credential},
        rows={
            _CRED_ID: (
                "weftlyflow.slack_oauth2",
                {"access_token": "xoxb-oauth", "default_channel": "C42"},
                _PROJECT_ID,
            ),
        },
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "post_message", "text": "hi"},
        credentials={"slack_api": _CRED_ID},
    )
    await SlackNode().execute(_ctx_for(node, resolver=resolver), [Item()])
    assert route.calls.last.request.headers["authorization"] == "Bearer xoxb-oauth"
    body = json.loads(route.calls.last.request.content)
    assert body["channel"] == "C42"


@respx.mock
async def test_list_channels_returns_channels_array() -> None:
    route = respx.post("https://slack.com/api/conversations.list").mock(
        return_value=Response(
            200,
            json={
                "ok": True,
                "channels": [{"id": "C1", "name": "general"}, {"id": "C2", "name": "random"}],
                "response_metadata": {"next_cursor": ""},
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={
            "operation": "list_channels",
            "limit": 50,
            "types": "public_channel,private_channel",
            "exclude_archived": True,
        },
        credentials={"slack_api": _CRED_ID},
    )
    out = await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["operation"] == "list_channels"
    assert [c["name"] for c in result.json["channels"]] == ["general", "random"]
    body = json.loads(route.calls.last.request.content)
    assert body["limit"] == 50
    assert body["types"] == "public_channel,private_channel"
    assert body["exclude_archived"] is True


# --- error paths -----------------------------------------------------------


@respx.mock
async def test_slack_error_becomes_node_execution_error() -> None:
    respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=Response(200, json={"ok": False, "error": "channel_not_found"}),
    )
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "post_message", "channel": "#missing", "text": "hi"},
        credentials={"slack_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="channel_not_found"):
        await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "post_message", "channel": "#x", "text": "hi"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_token_raises() -> None:
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "post_message", "channel": "#x", "text": "hi"},
        credentials={"slack_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty access_token"):
        await SlackNode().execute(
            _ctx_for(node, resolver=_resolver(access_token="")), [Item()],
        )


async def test_unsupported_operation_raises() -> None:
    node = Node(
        id="node_1",
        name="Slack",
        type="weftlyflow.slack",
        parameters={"operation": "bogus"},
        credentials={"slack_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await SlackNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- operation builder (direct unit tests, no HTTP) ------------------------


def test_build_request_rejects_blocks_of_wrong_shape() -> None:
    with pytest.raises(ValueError, match="blocks"):
        build_request(
            "post_message",
            {"channel": "C1", "text": "x", "blocks": "not-a-list"},
        )


def test_build_request_post_message_requires_body() -> None:
    with pytest.raises(ValueError, match=r"text.*blocks|blocks.*text"):
        build_request("post_message", {"channel": "C1"})


def test_build_request_list_channels_validates_types() -> None:
    with pytest.raises(ValueError, match="unknown channel types"):
        build_request("list_channels", {"types": "nope"})


def test_build_request_list_channels_caps_limit() -> None:
    _, _, body = build_request("list_channels", {"limit": 10_000})
    assert body["limit"] == 1000


def test_build_request_list_channels_rejects_negative_limit() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        build_request("list_channels", {"limit": 0})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})


def test_build_request_add_reaction_strips_colons() -> None:
    _, _, body = build_request(
        "add_reaction",
        {"channel": "C1", "ts": "1.1", "emoji": ":eyes:"},
    )
    assert body == {"channel": "C1", "timestamp": "1.1", "name": "eyes"}


def test_build_request_add_reaction_requires_emoji() -> None:
    with pytest.raises(ValueError, match="emoji"):
        build_request("add_reaction", {"channel": "C1", "ts": "1.1"})


def test_build_request_get_channel_history_caps_limit() -> None:
    _, _, body = build_request(
        "get_channel_history",
        {"channel": "C1", "limit": 5000},
    )
    assert body["limit"] == 1000


def test_build_request_list_users_defaults_limit() -> None:
    _, _, body = build_request("list_users", {})
    assert body == {"limit": 100}
