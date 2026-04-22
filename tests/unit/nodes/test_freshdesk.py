"""Unit tests for :class:`FreshdeskNode`.

Exercises every supported operation against a respx-mocked Freshdesk
v2 REST API. Verifies the distinctive Basic-auth shape where the
api_key is the username and the password is a literal ``X``, the
per-tenant subdomain base URL, the priority/status/source
string→integer coercion, the contact-requires-contact-method rule,
and the error envelope parsing.
"""

from __future__ import annotations

import json
from base64 import b64encode

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import FreshdeskApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.freshdesk import FreshdeskNode
from weftlyflow.nodes.integrations.freshdesk.operations import build_request

_CRED_ID: str = "cr_fd"
_PROJECT_ID: str = "pr_test"
_SUBDOMAIN: str = "acme"
_BASE: str = f"https://{_SUBDOMAIN}.freshdesk.com/api/v2"
_API_KEY: str = "fk-abc"


def _resolver(
    *,
    api_key: str = _API_KEY,
    subdomain: str = _SUBDOMAIN,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.freshdesk_api": FreshdeskApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.freshdesk_api",
                {"api_key": api_key, "subdomain": subdomain},
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


def _expected_basic_header() -> str:
    pair = f"{_API_KEY}:X".encode()
    return "Basic " + b64encode(pair).decode("ascii")


# --- list_tickets / get_ticket -----------------------------------------


@respx.mock
async def test_list_tickets_uses_basic_api_key_colon_x() -> None:
    route = respx.get(f"{_BASE}/tickets").mock(
        return_value=Response(200, json=[{"id": 1}]),
    )
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={
            "operation": "list_tickets",
            "per_page": 20,
            "updated_since": "2026-04-01T00:00:00Z",
        },
        credentials={"freshdesk_api": _CRED_ID},
    )
    await FreshdeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == _expected_basic_header()
    url = str(request.url)
    assert "per_page=20" in url
    assert "updated_since=2026-04-01" in url


@respx.mock
async def test_get_ticket_targets_ticket_path() -> None:
    route = respx.get(f"{_BASE}/tickets/123").mock(
        return_value=Response(200, json={"id": 123}),
    )
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={"operation": "get_ticket", "ticket_id": "123"},
        credentials={"freshdesk_api": _CRED_ID},
    )
    await FreshdeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- create_ticket -----------------------------------------------------


@respx.mock
async def test_create_ticket_coerces_enum_labels_to_integers() -> None:
    route = respx.post(f"{_BASE}/tickets").mock(
        return_value=Response(201, json={"id": 7}),
    )
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={
            "operation": "create_ticket",
            "subject": "Payment failed",
            "description": "Retry exhausted",
            "email": "ada@example.com",
            "priority": "high",
            "status": "pending",
            "source": "email",
            "type": "Billing",
            "tags": "billing, retry",
        },
        credentials={"freshdesk_api": _CRED_ID},
    )
    await FreshdeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "subject": "Payment failed",
        "description": "Retry exhausted",
        "email": "ada@example.com",
        "priority": 3,
        "status": 3,
        "source": 1,
        "type": "Billing",
        "tags": ["billing", "retry"],
    }


def test_create_ticket_rejects_invalid_priority() -> None:
    with pytest.raises(ValueError, match="invalid priority"):
        build_request(
            "create_ticket",
            {
                "subject": "x",
                "description": "y",
                "email": "a@x.io",
                "priority": "bogus",
            },
        )


# --- update_ticket -----------------------------------------------------


@respx.mock
async def test_update_ticket_coerces_labels_inside_fields() -> None:
    route = respx.put(f"{_BASE}/tickets/9").mock(
        return_value=Response(200, json={"id": 9}),
    )
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={
            "operation": "update_ticket",
            "ticket_id": "9",
            "fields": {"priority": "urgent", "status": "resolved"},
        },
        credentials={"freshdesk_api": _CRED_ID},
    )
    await FreshdeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"priority": 4, "status": 4}


def test_update_ticket_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown ticket field"):
        build_request(
            "update_ticket",
            {"ticket_id": "9", "fields": {"bogus": "x"}},
        )


# --- create_contact / list_contacts ------------------------------------


@respx.mock
async def test_create_contact_requires_contact_method() -> None:
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={"operation": "create_contact", "name": "Nishant"},
        credentials={"freshdesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="one of 'email'"):
        await FreshdeskNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


@respx.mock
async def test_create_contact_posts_identity_and_company() -> None:
    route = respx.post(f"{_BASE}/contacts").mock(
        return_value=Response(201, json={"id": 3}),
    )
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={
            "operation": "create_contact",
            "name": "Nishant",
            "email": "n@example.com",
            "phone": "+1-555",
            "company_id": "42",
        },
        credentials={"freshdesk_api": _CRED_ID},
    )
    await FreshdeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "name": "Nishant",
        "email": "n@example.com",
        "phone": "+1-555",
        "company_id": 42,
    }


@respx.mock
async def test_list_contacts_filters_by_email() -> None:
    route = respx.get(f"{_BASE}/contacts").mock(
        return_value=Response(200, json=[]),
    )
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={
            "operation": "list_contacts",
            "email": "a@x.io",
        },
        credentials={"freshdesk_api": _CRED_ID},
    )
    await FreshdeskNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    url = str(route.calls.last.request.url)
    assert "email=a%40x.io" in url or "email=a@x.io" in url


# --- errors / credentials ----------------------------------------------


@respx.mock
async def test_api_error_surfaces_description_and_message() -> None:
    respx.get(f"{_BASE}/tickets").mock(
        return_value=Response(
            400,
            json={
                "description": "Validation failed",
                "errors": [{"message": "email is invalid"}],
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={"operation": "list_tickets"},
        credentials={"freshdesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Validation failed: email is invalid"):
        await FreshdeskNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={"operation": "list_tickets"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await FreshdeskNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_empty_subdomain_raises() -> None:
    node = Node(
        id="node_1",
        name="Freshdesk",
        type="weftlyflow.freshdesk",
        parameters={"operation": "list_tickets"},
        credentials={"freshdesk_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="subdomain"):
        await FreshdeskNode().execute(
            _ctx_for(node, resolver=_resolver(subdomain="")), [Item()],
        )


# --- direct builder unit tests -----------------------------------------


def test_build_list_caps_per_page_at_max() -> None:
    _, _, _, query = build_request("list_tickets", {"per_page": 9_999})
    assert query["per_page"] == 100


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("explode_desk", {})
