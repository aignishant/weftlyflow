"""Unit tests for :class:`CloudflareNode`.

Exercises every supported operation against a respx-mocked Cloudflare
client/v4 REST API. Verifies the distinctive dual-header scheme
``X-Auth-Email`` + ``X-Auth-Key`` (both must be present, and neither is
``Authorization``), the DNS record type allowlist, the TTL rule
(1 for auto or >=60), the unknown-field rejection on update, and the
``errors[].code: message`` envelope parsing.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import CloudflareApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.cloudflare import CloudflareNode
from weftlyflow.nodes.integrations.cloudflare.operations import build_request

_CRED_ID: str = "cr_cf"
_PROJECT_ID: str = "pr_test"
_BASE: str = "https://api.cloudflare.com/client/v4"


def _resolver(
    *,
    api_email: str = "ops@acme.io",
    api_key: str = "gk-123",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.cloudflare_api": CloudflareApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.cloudflare_api",
                {"api_email": api_email, "api_key": api_key},
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


# --- list_zones / get_zone ---------------------------------------------


@respx.mock
async def test_list_zones_sends_dual_x_auth_headers() -> None:
    route = respx.get(f"{_BASE}/zones").mock(
        return_value=Response(200, json={"result": [{"id": "z1"}]}),
    )
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={
            "operation": "list_zones",
            "per_page": 10,
            "name": "acme.io",
        },
        credentials={"cloudflare_api": _CRED_ID},
    )
    await CloudflareNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["X-Auth-Email"] == "ops@acme.io"
    assert request.headers["X-Auth-Key"] == "gk-123"
    assert "authorization" not in request.headers
    url = str(request.url)
    assert "per_page=10" in url
    assert "name=acme.io" in url


@respx.mock
async def test_get_zone_targets_zone_path() -> None:
    route = respx.get(f"{_BASE}/zones/z1").mock(
        return_value=Response(200, json={"result": {"id": "z1"}}),
    )
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={"operation": "get_zone", "zone_id": "z1"},
        credentials={"cloudflare_api": _CRED_ID},
    )
    await CloudflareNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- list_dns_records --------------------------------------------------


@respx.mock
async def test_list_dns_records_filters_by_type() -> None:
    route = respx.get(f"{_BASE}/zones/z1/dns_records").mock(
        return_value=Response(200, json={"result": [{"id": "r1"}]}),
    )
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={
            "operation": "list_dns_records",
            "zone_id": "z1",
            "type": "A",
            "name": "api.acme.io",
        },
        credentials={"cloudflare_api": _CRED_ID},
    )
    await CloudflareNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    url = str(route.calls.last.request.url)
    assert "type=A" in url
    assert "name=api.acme.io" in url


# --- create_dns_record -------------------------------------------------


@respx.mock
async def test_create_dns_record_posts_typed_body() -> None:
    route = respx.post(f"{_BASE}/zones/z1/dns_records").mock(
        return_value=Response(200, json={"result": {"id": "r1"}}),
    )
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={
            "operation": "create_dns_record",
            "zone_id": "z1",
            "type": "A",
            "name": "api.acme.io",
            "content": "192.0.2.1",
            "ttl": 300,
            "proxied": True,
        },
        credentials={"cloudflare_api": _CRED_ID},
    )
    await CloudflareNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "type": "A",
        "name": "api.acme.io",
        "content": "192.0.2.1",
        "ttl": 300,
        "proxied": True,
    }


def test_create_dns_record_rejects_invalid_type() -> None:
    with pytest.raises(ValueError, match="invalid dns record type"):
        build_request(
            "create_dns_record",
            {
                "zone_id": "z1",
                "type": "ZZZ",
                "name": "x.io",
                "content": "1.1.1.1",
            },
        )


def test_create_dns_record_rejects_invalid_ttl() -> None:
    with pytest.raises(ValueError, match="'ttl' must be 1"):
        build_request(
            "create_dns_record",
            {
                "zone_id": "z1",
                "type": "A",
                "name": "x.io",
                "content": "1.1.1.1",
                "ttl": 30,
            },
        )


# --- update_dns_record -------------------------------------------------


@respx.mock
async def test_update_dns_record_patches_with_fields() -> None:
    route = respx.patch(f"{_BASE}/zones/z1/dns_records/r1").mock(
        return_value=Response(200, json={"result": {"id": "r1"}}),
    )
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={
            "operation": "update_dns_record",
            "zone_id": "z1",
            "record_id": "r1",
            "fields": {"content": "192.0.2.2", "ttl": 600},
        },
        credentials={"cloudflare_api": _CRED_ID},
    )
    await CloudflareNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"content": "192.0.2.2", "ttl": 600}


def test_update_dns_record_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown dns record field"):
        build_request(
            "update_dns_record",
            {"zone_id": "z1", "record_id": "r1", "fields": {"bogus": "x"}},
        )


# --- delete_dns_record -------------------------------------------------


@respx.mock
async def test_delete_dns_record_issues_delete_verb() -> None:
    route = respx.delete(f"{_BASE}/zones/z1/dns_records/r1").mock(
        return_value=Response(200, json={"result": {"id": "r1"}}),
    )
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={
            "operation": "delete_dns_record",
            "zone_id": "z1",
            "record_id": "r1",
        },
        credentials={"cloudflare_api": _CRED_ID},
    )
    await CloudflareNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- errors / credentials ----------------------------------------------


@respx.mock
async def test_api_error_surfaces_errors_envelope() -> None:
    respx.get(f"{_BASE}/zones").mock(
        return_value=Response(
            403,
            json={
                "success": False,
                "errors": [{"code": 9103, "message": "unknown X-Auth-Key"}],
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={"operation": "list_zones"},
        credentials={"cloudflare_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="9103: unknown X-Auth-Key"):
        await CloudflareNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={"operation": "list_zones"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await CloudflareNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_empty_api_email_raises() -> None:
    node = Node(
        id="node_1",
        name="Cloudflare",
        type="weftlyflow.cloudflare",
        parameters={"operation": "list_zones"},
        credentials={"cloudflare_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="api_email"):
        await CloudflareNode().execute(
            _ctx_for(node, resolver=_resolver(api_email="")), [Item()],
        )


# --- direct builder unit tests -----------------------------------------


def test_build_list_caps_per_page_at_max() -> None:
    _, _, _, query = build_request("list_zones", {"per_page": 9_999})
    assert query["per_page"] == 1000


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("purge_cache", {})
