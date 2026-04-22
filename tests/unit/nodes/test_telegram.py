"""Unit tests for :class:`TelegramNode`.

Exercises every supported operation against a respx-mocked Telegram Bot
API. Verifies that the bot token is embedded in the URL path — not a
header — and that Telegram's ``ok``/``description`` envelope is
reflected in the node output and errors.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import TelegramBotCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.telegram import TelegramNode
from weftlyflow.nodes.integrations.telegram.operations import build_request

_CRED_ID: str = "cr_tg"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "123456:ABC-xyz"
_BOT_PREFIX: str = f"https://api.telegram.org/bot{_TOKEN}"


def _resolver(*, bot_token: str = _TOKEN) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.telegram_bot": TelegramBotCredential},
        rows={
            _CRED_ID: ("weftlyflow.telegram_bot", {"bot_token": bot_token}, _PROJECT_ID),
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


# --- send_message ---------------------------------------------------------


@respx.mock
async def test_send_message_embeds_token_in_path() -> None:
    route = respx.post(f"{_BOT_PREFIX}/sendMessage").mock(
        return_value=Response(200, json={"ok": True, "result": {"message_id": 42}}),
    )
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "send_message",
            "chat_id": "@weftly",
            "text": "hello world",
        },
        credentials={"telegram_bot": _CRED_ID},
    )
    out = await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["ok"] is True
    assert result.json["response"]["message_id"] == 42
    request = route.calls.last.request
    body = json.loads(request.content)
    assert body == {"chat_id": "@weftly", "text": "hello world"}
    assert "authorization" not in request.headers


@respx.mock
async def test_send_message_applies_parse_mode_and_reply() -> None:
    route = respx.post(f"{_BOT_PREFIX}/sendMessage").mock(
        return_value=Response(200, json={"ok": True, "result": {}}),
    )
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "send_message",
            "chat_id": 12345,
            "text": "*bold*",
            "parse_mode": "MarkdownV2",
            "disable_notification": True,
            "reply_to_message_id": 99,
        },
        credentials={"telegram_bot": _CRED_ID},
    )
    await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["chat_id"] == 12345
    assert body["parse_mode"] == "MarkdownV2"
    assert body["disable_notification"] is True
    assert body["reply_to_message_id"] == 99


# --- send_photo / edit / delete ------------------------------------------


@respx.mock
async def test_send_photo_requires_photo_field() -> None:
    route = respx.post(f"{_BOT_PREFIX}/sendPhoto").mock(
        return_value=Response(200, json={"ok": True, "result": {"message_id": 1}}),
    )
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "send_photo",
            "chat_id": "@x",
            "photo": "https://example.com/cat.png",
            "caption": "kitty",
        },
        credentials={"telegram_bot": _CRED_ID},
    )
    await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["photo"] == "https://example.com/cat.png"
    assert body["caption"] == "kitty"


@respx.mock
async def test_edit_message_text_includes_message_id() -> None:
    route = respx.post(f"{_BOT_PREFIX}/editMessageText").mock(
        return_value=Response(200, json={"ok": True, "result": {"message_id": 7}}),
    )
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "edit_message_text",
            "chat_id": "@x",
            "message_id": 7,
            "text": "updated",
        },
        credentials={"telegram_bot": _CRED_ID},
    )
    await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"chat_id": "@x", "message_id": 7, "text": "updated"}


@respx.mock
async def test_delete_message_posts_chat_and_message_id() -> None:
    route = respx.post(f"{_BOT_PREFIX}/deleteMessage").mock(
        return_value=Response(200, json={"ok": True, "result": True}),
    )
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "delete_message",
            "chat_id": "@x",
            "message_id": 5,
        },
        credentials={"telegram_bot": _CRED_ID},
    )
    out = await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"] is True
    body = json.loads(route.calls.last.request.content)
    assert body == {"chat_id": "@x", "message_id": 5}


@respx.mock
async def test_get_updates_accepts_empty_body() -> None:
    route = respx.post(f"{_BOT_PREFIX}/getUpdates").mock(
        return_value=Response(200, json={"ok": True, "result": []}),
    )
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={"operation": "get_updates"},
        credentials={"telegram_bot": _CRED_ID},
    )
    out = await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"] == []
    assert route.called


# --- error paths ----------------------------------------------------------


@respx.mock
async def test_api_envelope_ok_false_raises() -> None:
    respx.post(f"{_BOT_PREFIX}/sendMessage").mock(
        return_value=Response(
            200,
            json={"ok": False, "description": "Bad Request: chat not found"},
        ),
    )
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "send_message",
            "chat_id": "@missing",
            "text": "hi",
        },
        credentials={"telegram_bot": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="chat not found"):
        await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_http_error_surfaces_description() -> None:
    respx.post(f"{_BOT_PREFIX}/sendMessage").mock(
        return_value=Response(
            403,
            json={"ok": False, "description": "Forbidden: bot was blocked"},
        ),
    )
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "send_message",
            "chat_id": "@x",
            "text": "hi",
        },
        credentials={"telegram_bot": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Forbidden"):
        await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "send_message",
            "chat_id": "@x",
            "text": "hi",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await TelegramNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_bot_token_raises() -> None:
    node = Node(
        id="node_1",
        name="Telegram",
        type="weftlyflow.telegram",
        parameters={
            "operation": "send_message",
            "chat_id": "@x",
            "text": "hi",
        },
        credentials={"telegram_bot": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'bot_token'"):
        await TelegramNode().execute(
            _ctx_for(node, resolver=_resolver(bot_token="")), [Item()],
        )


# --- direct builder unit tests --------------------------------------------


def test_build_request_send_message_rejects_overlong_text() -> None:
    with pytest.raises(ValueError, match="at most 4096"):
        build_request(
            "send_message",
            {"chat_id": "@x", "text": "a" * 4097},
        )


def test_build_request_requires_chat_id() -> None:
    with pytest.raises(ValueError, match="'chat_id' is required"):
        build_request("send_message", {"text": "hi"})


def test_build_request_rejects_bad_parse_mode() -> None:
    with pytest.raises(ValueError, match="invalid parse_mode"):
        build_request(
            "send_message",
            {"chat_id": "@x", "text": "hi", "parse_mode": "wrong"},
        )


def test_build_request_delete_message_requires_message_id() -> None:
    with pytest.raises(ValueError, match="'message_id' is required"):
        build_request("delete_message", {"chat_id": "@x"})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
