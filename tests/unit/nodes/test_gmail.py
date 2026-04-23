"""Unit tests for :class:`GmailNode` and ``GmailOAuth2Credential``.

Exercises the distinctive base64url-encoded RFC 2822 MIME envelope in
``{"raw": "..."}`` that the Gmail send_message endpoint expects, the
percent-encoded message-id path segments, the ``/modify`` sub-resource
for label changes, and the Bearer-token credential injection path.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import GmailOAuth2Credential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.gmail import GmailNode
from weftlyflow.nodes.integrations.gmail.operations import (
    build_raw_message,
    build_request,
)

_CRED_ID: str = "cr_gmail"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "ya29.test-access-token"
_BASE: str = "https://gmail.googleapis.com/gmail/v1/users/me"


def _resolver(*, token: str = _TOKEN) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.gmail_oauth2": GmailOAuth2Credential},
        rows={
            _CRED_ID: (
                "weftlyflow.gmail_oauth2",
                {"access_token": token},
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


# --- credential ------------------------------------------------------


async def test_credential_inject_sets_bearer_token() -> None:
    request = httpx.Request("POST", f"{_BASE}/messages/send")
    out = await GmailOAuth2Credential().inject({"access_token": _TOKEN}, request)
    assert out.headers["Authorization"] == f"Bearer {_TOKEN}"


def test_credential_has_gmail_send_scope_default() -> None:
    props = {p.name: p for p in GmailOAuth2Credential.properties}
    assert "gmail.send" in str(props["scope"].default)


# --- send_message: base64url raw envelope ----------------------------


def test_build_raw_message_is_base64url_and_rfc2822() -> None:
    raw = build_raw_message(
        to="a@b.c", subject="hi", body_text="hello world",
    )
    assert "+" not in raw and "/" not in raw and "=" not in raw
    decoded = base64.urlsafe_b64decode(raw + "==")
    assert b"To: a@b.c" in decoded
    assert b"Subject: hi" in decoded
    assert b"hello world" in decoded


@respx.mock
async def test_send_message_composes_raw_when_raw_absent() -> None:
    route = respx.post(f"{_BASE}/messages/send").mock(
        return_value=Response(200, json={"id": "m1"}),
    )
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={
            "operation": "send_message",
            "to": "dest@example.com",
            "subject": "Greetings",
            "body": "Hello there.",
        },
        credentials={"gmail_oauth2": _CRED_ID},
    )
    await GmailNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert "raw" in body
    decoded = base64.urlsafe_b64decode(body["raw"] + "==")
    assert b"dest@example.com" in decoded
    assert b"Greetings" in decoded


@respx.mock
async def test_send_message_passes_raw_through_untouched() -> None:
    route = respx.post(f"{_BASE}/messages/send").mock(
        return_value=Response(200, json={"id": "m2"}),
    )
    precomposed = "SGVsbG8tcHJlLWNvbXBvc2Vk"
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={"operation": "send_message", "raw": precomposed},
        credentials={"gmail_oauth2": _CRED_ID},
    )
    await GmailNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"raw": precomposed}


@respx.mock
async def test_send_message_includes_thread_id() -> None:
    route = respx.post(f"{_BASE}/messages/send").mock(
        return_value=Response(200, json={"id": "m3"}),
    )
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={
            "operation": "send_message",
            "raw": "eA==",
            "thread_id": "thread-abc",
        },
        credentials={"gmail_oauth2": _CRED_ID},
    )
    await GmailNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["threadId"] == "thread-abc"


def test_send_message_requires_raw_or_body() -> None:
    with pytest.raises(ValueError, match="'raw' or 'body'"):
        build_request("send_message", {"to": "a@b", "subject": "s"})


# --- list_messages --------------------------------------------------


@respx.mock
async def test_list_messages_forwards_query_params() -> None:
    route = respx.get(f"{_BASE}/messages").mock(
        return_value=Response(200, json={"messages": []}),
    )
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={
            "operation": "list_messages",
            "q": "from:alerts@",
            "maxResults": 5,
            "includeSpamTrash": False,
        },
        credentials={"gmail_oauth2": _CRED_ID},
    )
    await GmailNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["q"] == "from:alerts@"
    assert params["maxResults"] == "5"
    assert params["includeSpamTrash"] == "false"


# --- get_message ----------------------------------------------------


@respx.mock
async def test_get_message_percent_encodes_id() -> None:
    route = respx.get(f"{_BASE}/messages/abc%2F123").mock(
        return_value=Response(200, json={"id": "abc/123"}),
    )
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={
            "operation": "get_message",
            "message_id": "abc/123",
            "format": "metadata",
        },
        credentials={"gmail_oauth2": _CRED_ID},
    )
    await GmailNode().execute(_ctx_for(node), [Item()])
    assert route.called
    assert route.calls.last.request.url.params["format"] == "metadata"


# --- trash_message --------------------------------------------------


@respx.mock
async def test_trash_message_posts_to_trash_subresource() -> None:
    route = respx.post(f"{_BASE}/messages/m1/trash").mock(
        return_value=Response(200, json={"id": "m1"}),
    )
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={"operation": "trash_message", "message_id": "m1"},
        credentials={"gmail_oauth2": _CRED_ID},
    )
    await GmailNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- add_label: /modify endpoint ------------------------------------


@respx.mock
async def test_add_label_posts_modify_body() -> None:
    route = respx.post(f"{_BASE}/messages/m1/modify").mock(
        return_value=Response(200, json={"id": "m1"}),
    )
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={
            "operation": "add_label",
            "message_id": "m1",
            "add_label_ids": ["Label_1"],
            "remove_label_ids": ["UNREAD"],
        },
        credentials={"gmail_oauth2": _CRED_ID},
    )
    await GmailNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"addLabelIds": ["Label_1"], "removeLabelIds": ["UNREAD"]}


def test_add_label_requires_at_least_one_list() -> None:
    with pytest.raises(ValueError, match="add_label_ids"):
        build_request("add_label", {"message_id": "m1"})


# --- errors ---------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.post(f"{_BASE}/messages/send").mock(
        return_value=Response(403, json={"error": {"message": "insufficient scope"}}),
    )
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={"operation": "send_message", "raw": "eA=="},
        credentials={"gmail_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="insufficient scope"):
        await GmailNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={"operation": "send_message", "raw": "eA=="},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await GmailNode().execute(_ctx_for(node), [Item()])


async def test_empty_token_raises() -> None:
    resolver = _resolver(token="")
    node = Node(
        id="node_1",
        name="Gmail",
        type="weftlyflow.gmail",
        parameters={"operation": "send_message", "raw": "eA=="},
        credentials={"gmail_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'access_token'"):
        await GmailNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
