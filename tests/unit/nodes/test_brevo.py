"""Unit tests for :class:`BrevoNode`.

Exercises every supported operation against a respx-mocked Brevo v3
REST API. Verifies the lowercase ``api-key`` header, the
``{sender, to, subject}`` transactional-email payload shape, and the
comma-separated list coercion for recipients and contact lists.
"""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BrevoApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.brevo import BrevoNode
from weftlyflow.nodes.integrations.brevo.operations import build_request

_CRED_ID: str = "cr_brv"
_PROJECT_ID: str = "pr_test"
_BASE: str = "https://api.brevo.com/v3"


def _resolver(*, api_key: str = "xkeysib-abc") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.brevo_api": BrevoApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.brevo_api",
                {"api_key": api_key},
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


# --- send_email ---------------------------------------------------------


@respx.mock
async def test_send_email_posts_with_lowercase_api_key_header() -> None:
    route = respx.post(f"{_BASE}/smtp/email").mock(
        return_value=Response(201, json={"messageId": "<m1>"}),
    )
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={
            "operation": "send_email",
            "sender": {"email": "from@acme.io", "name": "Acme"},
            "to": "a@x.io, b@x.io",
            "subject": "Hi",
            "html_content": "<p>hello</p>",
            "tags": "campaign, welcome",
        },
        credentials={"brevo_api": _CRED_ID},
    )
    await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["api-key"] == "xkeysib-abc"
    assert "authorization" not in request.headers
    body = json.loads(request.content)
    assert body == {
        "sender": {"email": "from@acme.io", "name": "Acme"},
        "to": [{"email": "a@x.io"}, {"email": "b@x.io"}],
        "subject": "Hi",
        "htmlContent": "<p>hello</p>",
        "tags": ["campaign", "welcome"],
    }


@respx.mock
async def test_send_email_accepts_bare_sender_string() -> None:
    route = respx.post(f"{_BASE}/smtp/email").mock(
        return_value=Response(201, json={"messageId": "<m1>"}),
    )
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={
            "operation": "send_email",
            "sender": "from@acme.io",
            "to": [{"email": "a@x.io", "name": "Alice"}],
            "subject": "Hi",
            "text_content": "hello",
        },
        credentials={"brevo_api": _CRED_ID},
    )
    await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["sender"] == {"email": "from@acme.io"}
    assert body["to"] == [{"email": "a@x.io", "name": "Alice"}]
    assert body["textContent"] == "hello"


async def test_send_email_requires_content() -> None:
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={
            "operation": "send_email",
            "sender": "from@acme.io",
            "to": "a@x.io",
            "subject": "Hi",
        },
        credentials={"brevo_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="html_content"):
        await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- create_contact / update_contact / get_contact ----------------------


@respx.mock
async def test_create_contact_posts_update_enabled_and_list_ids() -> None:
    route = respx.post(f"{_BASE}/contacts").mock(
        return_value=Response(201, json={"id": 11}),
    )
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={
            "operation": "create_contact",
            "email": "new@acme.io",
            "attributes": {"FIRSTNAME": "Nishant"},
            "list_ids": "3, 7",
            "update_enabled": True,
        },
        credentials={"brevo_api": _CRED_ID},
    )
    await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "email": "new@acme.io",
        "attributes": {"FIRSTNAME": "Nishant"},
        "listIds": [3, 7],
        "updateEnabled": True,
    }


@respx.mock
async def test_update_contact_url_encodes_email_path() -> None:
    target_email = "a+tag@acme.io"
    encoded = quote(target_email, safe="")
    route = respx.put(f"{_BASE}/contacts/{encoded}").mock(
        return_value=Response(204),
    )
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={
            "operation": "update_contact",
            "email": target_email,
            "attributes": {"LASTNAME": "Gupta"},
            "unlink_list_ids": [2],
        },
        credentials={"brevo_api": _CRED_ID},
    )
    await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "attributes": {"LASTNAME": "Gupta"},
        "unlinkListIds": [2],
    }


async def test_update_contact_requires_at_least_one_patch_field() -> None:
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={
            "operation": "update_contact",
            "email": "a@x.io",
        },
        credentials={"brevo_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="update_contact"):
        await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_get_contact_is_a_get() -> None:
    encoded = quote("a@x.io", safe="")
    route = respx.get(f"{_BASE}/contacts/{encoded}").mock(
        return_value=Response(200, json={"id": 1}),
    )
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={"operation": "get_contact", "email": "a@x.io"},
        credentials={"brevo_api": _CRED_ID},
    )
    await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- add_contact_to_list ------------------------------------------------


@respx.mock
async def test_add_contact_to_list_coerces_emails_csv() -> None:
    route = respx.post(f"{_BASE}/contacts/lists/42/contacts/add").mock(
        return_value=Response(201, json={"contacts": {"success": []}}),
    )
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={
            "operation": "add_contact_to_list",
            "list_id": 42,
            "emails": "a@x.io, b@x.io",
        },
        credentials={"brevo_api": _CRED_ID},
    )
    await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"emails": ["a@x.io", "b@x.io"]}


# --- get_account / errors -----------------------------------------------


@respx.mock
async def test_get_account_is_a_get() -> None:
    route = respx.get(f"{_BASE}/account").mock(
        return_value=Response(200, json={"email": "admin@acme.io"}),
    )
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={"operation": "get_account"},
        credentials={"brevo_api": _CRED_ID},
    )
    out = await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["email"] == "admin@acme.io"
    assert route.called


@respx.mock
async def test_api_error_surfaces_code_and_message() -> None:
    respx.post(f"{_BASE}/smtp/email").mock(
        return_value=Response(
            400, json={"code": "invalid_parameter", "message": "sender is invalid"},
        ),
    )
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={
            "operation": "send_email",
            "sender": "nope@x",
            "to": "a@x.io",
            "subject": "x",
            "text_content": "y",
        },
        credentials={"brevo_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="sender is invalid"):
        await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={"operation": "get_account"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await BrevoNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_api_key_raises() -> None:
    node = Node(
        id="node_1",
        name="Brevo",
        type="weftlyflow.brevo",
        parameters={"operation": "get_account"},
        credentials={"brevo_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_key'"):
        await BrevoNode().execute(
            _ctx_for(node, resolver=_resolver(api_key="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_send_email_requires_sender() -> None:
    with pytest.raises(ValueError, match="'sender'"):
        build_request(
            "send_email",
            {"to": "a@x.io", "subject": "x", "text_content": "y"},
        )


def test_build_request_add_contact_to_list_requires_emails() -> None:
    with pytest.raises(ValueError, match="'emails'"):
        build_request("add_contact_to_list", {"list_id": 1})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_contact", {})
