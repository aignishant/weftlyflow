"""Unit tests for :class:`MailchimpNode`.

Exercises every supported operation against a respx-mocked Mailchimp
Marketing v3 REST API. Verifies the Basic auth header built from a
placeholder user + the API key, the datacenter segment parsed out of
the key's ``abc-us6`` suffix to compose the host, and the MD5
subscriber-hash used in member paths.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import MailchimpApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.mailchimp import MailchimpNode
from weftlyflow.nodes.integrations.mailchimp.operations import (
    build_request,
    subscriber_hash,
)

_CRED_ID: str = "cr_mc"
_PROJECT_ID: str = "pr_test"
_API_KEY: str = "abc123-us6"
_DATACENTER: str = "us6"
_BASE: str = f"https://{_DATACENTER}.api.mailchimp.com/3.0"


def _resolver(*, api_key: str = _API_KEY) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.mailchimp_api": MailchimpApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.mailchimp_api",
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


def _expected_basic_header(key: str = _API_KEY) -> str:
    encoded = base64.b64encode(f"weftlyflow:{key}".encode()).decode("ascii")
    return f"Basic {encoded}"


# --- list_lists ---------------------------------------------------------


@respx.mock
async def test_list_lists_uses_datacenter_host_and_basic_header() -> None:
    route = respx.get(f"{_BASE}/lists").mock(
        return_value=Response(200, json={"lists": [{"id": "L1"}]}),
    )
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={"operation": "list_lists", "count": 50, "offset": 100},
        credentials={"mailchimp_api": _CRED_ID},
    )
    out = await MailchimpNode().execute(
        _ctx_for(node, resolver=_resolver()), [Item()],
    )
    request = route.calls.last.request
    assert request.headers["Authorization"] == _expected_basic_header()
    query = str(request.url)
    assert "count=50" in query
    assert "offset=100" in query
    [result] = out[0]
    assert result.json["lists"] == [{"id": "L1"}]


@respx.mock
async def test_list_lists_caps_count_at_max() -> None:
    route = respx.get(f"{_BASE}/lists").mock(
        return_value=Response(200, json={"lists": []}),
    )
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={"operation": "list_lists", "count": 9_999},
        credentials={"mailchimp_api": _CRED_ID},
    )
    await MailchimpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert "count=1000" in str(route.calls.last.request.url)


# --- get_list -----------------------------------------------------------


@respx.mock
async def test_get_list_escapes_list_id_in_path() -> None:
    route = respx.get(f"{_BASE}/lists/abc%2Fdef").mock(
        return_value=Response(200, json={"id": "abc/def"}),
    )
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={"operation": "get_list", "list_id": "abc/def"},
        credentials={"mailchimp_api": _CRED_ID},
    )
    await MailchimpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- add_member ---------------------------------------------------------


@respx.mock
async def test_add_member_sends_email_status_and_merge_fields() -> None:
    route = respx.post(f"{_BASE}/lists/L1/members").mock(
        return_value=Response(201, json={"id": "h"}),
    )
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={
            "operation": "add_member",
            "list_id": "L1",
            "email": "a@acme.io",
            "status": "subscribed",
            "merge_fields": {"FNAME": "Nishant"},
            "tags": "beta, power",
        },
        credentials={"mailchimp_api": _CRED_ID},
    )
    await MailchimpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "email_address": "a@acme.io",
        "status": "subscribed",
        "merge_fields": {"FNAME": "Nishant"},
        "tags": ["beta", "power"],
    }


async def test_add_member_rejects_invalid_status() -> None:
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={
            "operation": "add_member",
            "list_id": "L1",
            "email": "a@acme.io",
            "status": "bogus",
        },
        credentials={"mailchimp_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid status"):
        await MailchimpNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- update_member ------------------------------------------------------


@respx.mock
async def test_update_member_patches_with_subscriber_hash_path() -> None:
    target = "A@Acme.IO"
    expected_hash = hashlib.md5(
        target.strip().lower().encode("utf-8"),
    ).hexdigest()
    route = respx.patch(
        f"{_BASE}/lists/L1/members/{expected_hash}",
    ).mock(return_value=Response(200, json={"id": expected_hash}))
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={
            "operation": "update_member",
            "list_id": "L1",
            "email": target,
            "fields": {"status": "unsubscribed"},
        },
        credentials={"mailchimp_api": _CRED_ID},
    )
    await MailchimpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"status": "unsubscribed"}


async def test_update_member_requires_non_empty_fields() -> None:
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={
            "operation": "update_member",
            "list_id": "L1",
            "email": "a@acme.io",
            "fields": {},
        },
        credentials={"mailchimp_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'fields'"):
        await MailchimpNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- get_member ---------------------------------------------------------


@respx.mock
async def test_get_member_uses_subscriber_hash() -> None:
    email = "a@acme.io"
    expected_hash = subscriber_hash(email)
    route = respx.get(
        f"{_BASE}/lists/L1/members/{expected_hash}",
    ).mock(return_value=Response(200, json={"id": expected_hash}))
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={
            "operation": "get_member",
            "list_id": "L1",
            "email": email,
        },
        credentials={"mailchimp_api": _CRED_ID},
    )
    await MailchimpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- tag_member ---------------------------------------------------------


@respx.mock
async def test_tag_member_posts_active_and_inactive_entries() -> None:
    email = "a@acme.io"
    route = respx.post(
        f"{_BASE}/lists/L1/members/{subscriber_hash(email)}/tags",
    ).mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={
            "operation": "tag_member",
            "list_id": "L1",
            "email": email,
            "add_tags": "vip, beta",
            "remove_tags": "legacy",
        },
        credentials={"mailchimp_api": _CRED_ID},
    )
    await MailchimpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "tags": [
            {"name": "vip", "status": "active"},
            {"name": "beta", "status": "active"},
            {"name": "legacy", "status": "inactive"},
        ],
    }


async def test_tag_member_requires_at_least_one_tag_set() -> None:
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={
            "operation": "tag_member",
            "list_id": "L1",
            "email": "a@acme.io",
        },
        credentials={"mailchimp_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="add_tags"):
        await MailchimpNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- errors / credentials -----------------------------------------------


@respx.mock
async def test_api_error_surfaces_detail_field() -> None:
    respx.get(f"{_BASE}/lists").mock(
        return_value=Response(
            401, json={"title": "API Key Invalid", "detail": "bad key"},
        ),
    )
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={"operation": "list_lists"},
        credentials={"mailchimp_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="bad key"):
        await MailchimpNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={"operation": "list_lists"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MailchimpNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_api_key_without_datacenter_suffix_raises() -> None:
    node = Node(
        id="node_1",
        name="Mailchimp",
        type="weftlyflow.mailchimp",
        parameters={"operation": "list_lists"},
        credentials={"mailchimp_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="datacenter"):
        await MailchimpNode().execute(
            _ctx_for(node, resolver=_resolver(api_key="nodash")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_list_lists_caps_count() -> None:
    _, _, _, query = build_request("list_lists", {"count": 5_000})
    assert query["count"] == 1000


def test_subscriber_hash_lowercases_and_strips() -> None:
    assert subscriber_hash("  A@Acme.IO  ") == subscriber_hash("a@acme.io")


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_member", {})
