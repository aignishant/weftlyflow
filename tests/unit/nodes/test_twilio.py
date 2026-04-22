"""Unit tests for :class:`TwilioNode`.

Exercises every supported operation against a respx-mocked Twilio
Messaging API. Verifies HTTP Basic auth from ``account_sid:auth_token``,
the Account-SID-embedded URL path, and the form-encoded body on
``send_sms`` (Twilio does not accept JSON bodies on Messages).
"""

from __future__ import annotations

import base64
from urllib.parse import parse_qsl

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import TwilioApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.twilio import TwilioNode
from weftlyflow.nodes.integrations.twilio.operations import build_request

_CRED_ID: str = "cr_tw"
_PROJECT_ID: str = "pr_test"
_SID: str = "AC1234567890"
_TOKEN: str = "tok_secret"
_BASE: str = f"https://api.twilio.com/2010-04-01/Accounts/{_SID}"


def _resolver(
    *, account_sid: str = _SID, auth_token: str = _TOKEN,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.twilio_api": TwilioApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.twilio_api",
                {"account_sid": account_sid, "auth_token": auth_token},
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


def _expected_basic(sid: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode("ascii")


# --- send_sms ------------------------------------------------------------


@respx.mock
async def test_send_sms_uses_basic_auth_and_form_body() -> None:
    route = respx.post(f"{_BASE}/Messages.json").mock(
        return_value=Response(201, json={"sid": "SMx", "status": "queued"}),
    )
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={
            "operation": "send_sms",
            "to": "+15551234567",
            "from": "+15557654321",
            "body": "Hi there",
            "media_urls": ["https://example.com/1.png", "https://example.com/2.png"],
        },
        credentials={"twilio_api": _CRED_ID},
    )
    out = await TwilioNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["sid"] == "SMx"
    request = route.calls.last.request
    assert request.headers["authorization"] == _expected_basic(_SID, _TOKEN)
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    pairs = parse_qsl(request.content.decode(), keep_blank_values=True)
    media = [v for k, v in pairs if k == "MediaUrl"]
    assert media == ["https://example.com/1.png", "https://example.com/2.png"]
    flat = dict(pairs)
    assert flat["To"] == "+15551234567"
    assert flat["From"] == "+15557654321"
    assert flat["Body"] == "Hi there"


@respx.mock
async def test_send_sms_accepts_messaging_service_sid_instead_of_from() -> None:
    route = respx.post(f"{_BASE}/Messages.json").mock(
        return_value=Response(201, json={"sid": "SMx"}),
    )
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={
            "operation": "send_sms",
            "to": "+15551234567",
            "messaging_service_sid": "MG12345",
            "body": "Hi",
        },
        credentials={"twilio_api": _CRED_ID},
    )
    await TwilioNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    pairs = dict(parse_qsl(route.calls.last.request.content.decode()))
    assert pairs["MessagingServiceSid"] == "MG12345"
    assert "From" not in pairs


# --- get / list / delete -------------------------------------------------


@respx.mock
async def test_get_message_hits_sid_path() -> None:
    route = respx.get(f"{_BASE}/Messages/SMx.json").mock(
        return_value=Response(200, json={"sid": "SMx"}),
    )
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={"operation": "get_message", "message_sid": "SMx"},
        credentials={"twilio_api": _CRED_ID},
    )
    await TwilioNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


@respx.mock
async def test_list_messages_surfaces_messages_convenience_key() -> None:
    route = respx.get(f"{_BASE}/Messages.json").mock(
        return_value=Response(
            200, json={"messages": [{"sid": "SM1"}, {"sid": "SM2"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={
            "operation": "list_messages",
            "to": "+15551234567",
            "page_size": 50,
        },
        credentials={"twilio_api": _CRED_ID},
    )
    out = await TwilioNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [m["sid"] for m in result.json["messages"]] == ["SM1", "SM2"]
    query = dict(route.calls.last.request.url.params)
    assert query == {"To": "+15551234567", "PageSize": "50"}


@respx.mock
async def test_list_messages_caps_page_size_at_1000() -> None:
    route = respx.get(f"{_BASE}/Messages.json").mock(
        return_value=Response(200, json={"messages": []}),
    )
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={"operation": "list_messages", "page_size": 99999},
        credentials={"twilio_api": _CRED_ID},
    )
    await TwilioNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert dict(route.calls.last.request.url.params)["PageSize"] == "1000"


@respx.mock
async def test_delete_message_issues_delete() -> None:
    route = respx.delete(f"{_BASE}/Messages/SMx.json").mock(
        return_value=Response(204),
    )
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={"operation": "delete_message", "message_sid": "SMx"},
        credentials={"twilio_api": _CRED_ID},
    )
    out = await TwilioNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["status"] == 204
    assert route.called


# --- error & credential paths -------------------------------------------


@respx.mock
async def test_api_error_surfaces_message_and_code() -> None:
    respx.post(f"{_BASE}/Messages.json").mock(
        return_value=Response(
            400,
            json={"code": 21211, "message": "Invalid 'To' number", "more_info": "..."},
        ),
    )
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={
            "operation": "send_sms",
            "to": "bogus",
            "from": "+15557654321",
            "body": "Hi",
        },
        credentials={"twilio_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Invalid 'To' number"):
        await TwilioNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={"operation": "get_message", "message_sid": "SMx"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await TwilioNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_credential_fields_raise() -> None:
    node = Node(
        id="node_1",
        name="Twilio",
        type="weftlyflow.twilio",
        parameters={"operation": "get_message", "message_sid": "SMx"},
        credentials={"twilio_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'account_sid' and 'auth_token'"):
        await TwilioNode().execute(
            _ctx_for(node, resolver=_resolver(auth_token="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_send_sms_requires_from_or_service() -> None:
    with pytest.raises(ValueError, match="'from' or 'messaging_service_sid'"):
        build_request("send_sms", {"to": "+15551234567", "body": "Hi"})


def test_build_request_send_sms_requires_body() -> None:
    with pytest.raises(ValueError, match="'body' is required"):
        build_request(
            "send_sms", {"to": "+15551234567", "from": "+15557654321"},
        )


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("send_carrier_pigeon", {})
