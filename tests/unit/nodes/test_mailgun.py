"""Unit tests for :class:`MailgunNode`.

Exercises the ``send_email`` operation against a respx-mocked Mailgun v3
Messages API. Verifies HTTP Basic authentication, form-encoded bodies
with repeated ``to``/``cc``/``bcc``/``o:tag`` fields, US/EU region
routing, and tracking-flag translation.
"""

from __future__ import annotations

import base64

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BasicAuthCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.mailgun import MailgunNode

_CRED_ID: str = "cr_mg"
_PROJECT_ID: str = "pr_test"
_US_URL: str = "https://api.mailgun.net/v3/mg.example.com/messages"
_EU_URL: str = "https://api.eu.mailgun.net/v3/mg.example.com/messages"


def _resolver(
    *,
    username: str = "api",
    password: str = "key-abc",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.basic_auth": BasicAuthCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.basic_auth",
                {"username": username, "password": password},
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


def _parse_form(content: bytes) -> list[tuple[str, str]]:
    from urllib.parse import parse_qsl

    return parse_qsl(content.decode(), keep_blank_values=True)


# --- send_email (US) ------------------------------------------------------


@respx.mock
async def test_send_email_posts_form_body_with_basic_auth() -> None:
    route = respx.post(_US_URL).mock(
        return_value=Response(200, json={"id": "<msg@mg>", "message": "Queued"}),
    )
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "region": "us",
            "from_address": "Alice <alice@mg.example.com>",
            "to": "bob@example.com, carol@example.com",
            "subject": "Hello",
            "text": "Hi there",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    out = await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["id"] == "<msg@mg>"
    assert result.json["status"] == 200
    request = route.calls.last.request
    expected = "Basic " + base64.b64encode(b"api:key-abc").decode("ascii")
    assert request.headers["authorization"] == expected
    assert request.headers["content-type"].startswith(
        "application/x-www-form-urlencoded",
    )
    pairs = _parse_form(request.content)
    assert ("from", "Alice <alice@mg.example.com>") in pairs
    assert ("subject", "Hello") in pairs
    to_values = [v for k, v in pairs if k == "to"]
    assert to_values == ["bob@example.com", "carol@example.com"]
    assert ("text", "Hi there") in pairs


@respx.mock
async def test_send_email_repeats_cc_bcc_and_tags() -> None:
    route = respx.post(_US_URL).mock(return_value=Response(200, json={"id": "x"}))
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "b@x",
            "cc": "c1@x, c2@x",
            "bcc": "d1@x",
            "subject": "S",
            "html": "<p>hi</p>",
            "tags": "welcome, onboarding",
            "tracking": False,
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    pairs = _parse_form(route.calls.last.request.content)
    assert [v for k, v in pairs if k == "cc"] == ["c1@x", "c2@x"]
    assert [v for k, v in pairs if k == "bcc"] == ["d1@x"]
    assert [v for k, v in pairs if k == "o:tag"] == ["welcome", "onboarding"]
    assert ("o:tracking", "no") in pairs
    assert ("html", "<p>hi</p>") in pairs


@respx.mock
async def test_send_email_tracking_true_maps_to_yes() -> None:
    route = respx.post(_US_URL).mock(return_value=Response(200, json={"id": "x"}))
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
            "tracking": True,
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    pairs = _parse_form(route.calls.last.request.content)
    assert ("o:tracking", "yes") in pairs


# --- send_email (EU) ------------------------------------------------------


@respx.mock
async def test_send_email_eu_region_targets_eu_host() -> None:
    route = respx.post(_EU_URL).mock(return_value=Response(200, json={"id": "x"}))
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "region": "eu",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- error paths ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_message() -> None:
    respx.post(_US_URL).mock(
        return_value=Response(401, json={"message": "Forbidden"}),
    )
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Forbidden"):
        await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_network_error_wrapped_as_node_error() -> None:
    respx.post(_US_URL).mock(side_effect=httpx.ConnectError("boom"))
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="network error"):
        await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_credential_fields_raise() -> None:
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'username' and 'password'"):
        await MailgunNode().execute(
            _ctx_for(node, resolver=_resolver(password="")),
            [Item()],
        )


async def test_missing_domain_raises() -> None:
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'domain' is required"):
        await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_body_raises() -> None:
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match=r"'text'.*'html'"):
        await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_invalid_region_raises() -> None:
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "region": "asia",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid region"):
        await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_to_raises() -> None:
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_email",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "",
            "subject": "S",
            "text": "t",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="at least one address"):
        await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_unsupported_operation_raises() -> None:
    node = Node(
        id="node_1",
        name="Mailgun",
        type="weftlyflow.mailgun",
        parameters={
            "operation": "send_fax",
            "domain": "mg.example.com",
            "from_address": "a@x",
            "to": "b@x",
            "subject": "S",
            "text": "t",
        },
        credentials={"mailgun_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await MailgunNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
