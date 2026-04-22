"""Unit tests for :class:`SendGridNode`.

Exercises the single ``send_email`` operation against a respx-mocked
SendGrid v3 Mail Send endpoint. One behaviour per test (AAA).
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BearerTokenCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.sendgrid import SendGridNode

_CRED_ID: str = "cr_sendgrid"
_PROJECT_ID: str = "pr_test"
_MAIL_URL: str = "https://api.sendgrid.com/v3/mail/send"


def _resolver(
    *,
    token: str = "SG.abc",
    default_from_email: str = "",
    default_from_name: str = "",
) -> InMemoryCredentialResolver:
    payload: dict[str, object] = {"token": token}
    if default_from_email:
        payload["default_from_email"] = default_from_email
    if default_from_name:
        payload["default_from_name"] = default_from_name
    return InMemoryCredentialResolver(
        types={"weftlyflow.bearer_token": BearerTokenCredential},
        rows={_CRED_ID: ("weftlyflow.bearer_token", payload, _PROJECT_ID)},
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


# --- happy paths -----------------------------------------------------------


@respx.mock
async def test_send_email_builds_v3_body_and_surfaces_message_id() -> None:
    route = respx.post(_MAIL_URL).mock(
        return_value=Response(202, headers={"X-Message-Id": "msg_123"}),
    )
    node = Node(
        id="node_1",
        name="SendGrid",
        type="weftlyflow.sendgrid",
        parameters={
            "operation": "send_email",
            "from_email": "no-reply@acme.io",
            "from_name": "Acme",
            "to": "ada@example.com, grace@example.com",
            "subject": "hi",
            "text": "hello there",
            "html": "<p>hi</p>",
            "reply_to": "support@acme.io",
        },
        credentials={"sendgrid_api": _CRED_ID},
    )
    out = await SendGridNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["ok"] is True
    assert result.json["status"] == 202
    assert result.json["message_id"] == "msg_123"

    body = json.loads(route.calls.last.request.content)
    assert body["from"] == {"email": "no-reply@acme.io", "name": "Acme"}
    assert body["subject"] == "hi"
    assert body["reply_to"] == {"email": "support@acme.io"}
    assert body["personalizations"][0]["to"] == [
        {"email": "ada@example.com"},
        {"email": "grace@example.com"},
    ]
    content_types = [c["type"] for c in body["content"]]
    assert content_types == ["text/plain", "text/html"]
    headers = route.calls.last.request.headers
    assert headers["authorization"] == "Bearer SG.abc"


@respx.mock
async def test_send_email_falls_back_to_default_from_on_credential() -> None:
    route = respx.post(_MAIL_URL).mock(return_value=Response(202))
    node = Node(
        id="node_1",
        name="SendGrid",
        type="weftlyflow.sendgrid",
        parameters={
            "operation": "send_email",
            "to": "ada@example.com",
            "subject": "hi",
            "text": "hello",
        },
        credentials={"sendgrid_api": _CRED_ID},
    )
    resolver = _resolver(
        default_from_email="bot@acme.io", default_from_name="Acme Bot",
    )
    await SendGridNode().execute(_ctx_for(node, resolver=resolver), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["from"] == {"email": "bot@acme.io", "name": "Acme Bot"}


@respx.mock
async def test_send_email_with_cc_bcc_populates_personalization() -> None:
    route = respx.post(_MAIL_URL).mock(return_value=Response(202))
    node = Node(
        id="node_1",
        name="SendGrid",
        type="weftlyflow.sendgrid",
        parameters={
            "operation": "send_email",
            "from_email": "bot@acme.io",
            "to": "ada@example.com",
            "cc": "grace@example.com",
            "bcc": "audit@example.com, legal@example.com",
            "subject": "hi",
            "text": "hello",
        },
        credentials={"sendgrid_api": _CRED_ID},
    )
    await SendGridNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    personalization = json.loads(route.calls.last.request.content)["personalizations"][0]
    assert personalization["cc"] == [{"email": "grace@example.com"}]
    assert personalization["bcc"] == [
        {"email": "audit@example.com"},
        {"email": "legal@example.com"},
    ]


# --- validation errors -----------------------------------------------------


@respx.mock
async def test_missing_from_email_raises() -> None:
    node = Node(
        id="node_1",
        name="SendGrid",
        type="weftlyflow.sendgrid",
        parameters={
            "operation": "send_email",
            "to": "ada@example.com",
            "subject": "hi",
            "text": "hello",
        },
        credentials={"sendgrid_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="from_email"):
        await SendGridNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_missing_body_raises() -> None:
    node = Node(
        id="node_1",
        name="SendGrid",
        type="weftlyflow.sendgrid",
        parameters={
            "operation": "send_email",
            "from_email": "bot@acme.io",
            "to": "ada@example.com",
            "subject": "hi",
        },
        credentials={"sendgrid_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match=r"text.*html"):
        await SendGridNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_api_error_surfaces_first_message() -> None:
    respx.post(_MAIL_URL).mock(
        return_value=Response(
            400,
            json={"errors": [{"message": "from email invalid"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="SendGrid",
        type="weftlyflow.sendgrid",
        parameters={
            "operation": "send_email",
            "from_email": "bad",
            "to": "ada@example.com",
            "subject": "hi",
            "text": "hello",
        },
        credentials={"sendgrid_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="from email invalid"):
        await SendGridNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="SendGrid",
        type="weftlyflow.sendgrid",
        parameters={
            "operation": "send_email",
            "from_email": "bot@acme.io",
            "to": "ada@example.com",
            "subject": "hi",
            "text": "hello",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await SendGridNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_unsupported_operation_raises() -> None:
    node = Node(
        id="node_1",
        name="SendGrid",
        type="weftlyflow.sendgrid",
        parameters={"operation": "bogus"},
        credentials={"sendgrid_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await SendGridNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
