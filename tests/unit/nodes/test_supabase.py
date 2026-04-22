"""Unit tests for :class:`SupabaseNode`.

Exercises every supported operation against a respx-mocked Supabase
PostgREST surface. Verifies the distinctive dual-header scheme
``apikey`` + ``Authorization: Bearer`` (same key in both), the
credential-owned project URL, the PostgREST filter shape
(``col=eq.val``), the ``Prefer: return=representation`` header on write
operations, the ``Prefer: resolution=merge-duplicates`` on upsert, and
the guard that update/delete require filters.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import SupabaseApiCredential
from weftlyflow.credentials.types.supabase_api import project_url_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.supabase import SupabaseNode
from weftlyflow.nodes.integrations.supabase.operations import build_request

_CRED_ID: str = "cr_sb"
_PROJECT_ID: str = "pr_test"
_PROJECT_URL: str = "https://abcd.supabase.co"
_KEY: str = "sb-key-123"
_BASE: str = f"{_PROJECT_URL}/rest/v1"


def _resolver(
    *,
    key: str = _KEY,
    project_url: str = _PROJECT_URL,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.supabase_api": SupabaseApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.supabase_api",
                {"service_role_key": key, "project_url": project_url},
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


# --- select ------------------------------------------------------------


@respx.mock
async def test_select_sends_dual_apikey_and_bearer_headers() -> None:
    route = respx.get(f"{_BASE}/posts").mock(
        return_value=Response(200, json=[{"id": 1}]),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={
            "operation": "select",
            "table": "posts",
            "select": "id,title",
            "filters": {"published": "eq.true"},
            "order": "created_at.desc",
            "limit": 10,
        },
        credentials={"supabase_api": _CRED_ID},
    )
    out = await SupabaseNode().execute(
        _ctx_for(node, resolver=_resolver()), [Item()],
    )
    request = route.calls.last.request
    assert request.headers["apikey"] == _KEY
    assert request.headers["Authorization"] == f"Bearer {_KEY}"
    url = str(request.url)
    assert "select=id%2Ctitle" in url or "select=id,title" in url
    assert "published=eq.true" in url
    assert "order=created_at.desc" in url
    assert "limit=10" in url
    [result] = out[0]
    assert result.json["data"] == [{"id": 1}]


@respx.mock
async def test_select_coerces_bare_values_into_eq_prefix() -> None:
    route = respx.get(f"{_BASE}/posts").mock(
        return_value=Response(200, json=[]),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={
            "operation": "select",
            "table": "posts",
            "filters": {"id": 42},
        },
        credentials={"supabase_api": _CRED_ID},
    )
    await SupabaseNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    url = str(route.calls.last.request.url)
    assert "id=eq.42" in url


# --- insert ------------------------------------------------------------


@respx.mock
async def test_insert_sends_return_representation_prefer_header() -> None:
    route = respx.post(f"{_BASE}/posts").mock(
        return_value=Response(201, json=[{"id": 1, "title": "hi"}]),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={
            "operation": "insert",
            "table": "posts",
            "rows": [{"title": "hi"}],
        },
        credentials={"supabase_api": _CRED_ID},
    )
    await SupabaseNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["Prefer"] == "return=representation"
    assert json.loads(request.content) == [{"title": "hi"}]


@respx.mock
async def test_insert_accepts_single_dict_row() -> None:
    route = respx.post(f"{_BASE}/posts").mock(
        return_value=Response(201, json=[{"id": 1}]),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={
            "operation": "insert",
            "table": "posts",
            "rows": {"title": "one"},
        },
        credentials={"supabase_api": _CRED_ID},
    )
    await SupabaseNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert json.loads(route.calls.last.request.content) == {"title": "one"}


# --- update ------------------------------------------------------------


@respx.mock
async def test_update_requires_filters() -> None:
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={
            "operation": "update",
            "table": "posts",
            "fields": {"title": "x"},
        },
        credentials={"supabase_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="at least one 'filters'"):
        await SupabaseNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


@respx.mock
async def test_update_patches_with_filters_and_fields() -> None:
    route = respx.patch(f"{_BASE}/posts").mock(
        return_value=Response(200, json=[{"id": 1}]),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={
            "operation": "update",
            "table": "posts",
            "fields": {"title": "edited"},
            "filters": {"id": "eq.1"},
        },
        credentials={"supabase_api": _CRED_ID},
    )
    await SupabaseNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert "id=eq.1" in str(request.url)
    assert json.loads(request.content) == {"title": "edited"}


# --- delete ------------------------------------------------------------


@respx.mock
async def test_delete_requires_filters() -> None:
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={"operation": "delete", "table": "posts"},
        credentials={"supabase_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="at least one 'filters'"):
        await SupabaseNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


@respx.mock
async def test_delete_issues_delete_verb() -> None:
    route = respx.delete(f"{_BASE}/posts").mock(
        return_value=Response(204, json=[]),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={
            "operation": "delete",
            "table": "posts",
            "filters": {"id": "eq.1"},
        },
        credentials={"supabase_api": _CRED_ID},
    )
    await SupabaseNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- upsert ------------------------------------------------------------


@respx.mock
async def test_upsert_adds_merge_duplicates_prefer_header() -> None:
    route = respx.post(f"{_BASE}/posts").mock(
        return_value=Response(200, json=[{"id": 1}]),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={
            "operation": "upsert",
            "table": "posts",
            "rows": [{"id": 1, "title": "merged"}],
            "on_conflict": "id",
        },
        credentials={"supabase_api": _CRED_ID},
    )
    await SupabaseNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    prefer = request.headers["Prefer"]
    assert "return=representation" in prefer
    assert "resolution=merge-duplicates" in prefer
    assert "on_conflict=id" in str(request.url)


# --- project URL normalization -----------------------------------------


@respx.mock
async def test_project_url_without_scheme_gets_https() -> None:
    route = respx.get(f"{_BASE}/posts").mock(
        return_value=Response(200, json=[]),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={"operation": "select", "table": "posts"},
        credentials={"supabase_api": _CRED_ID},
    )
    await SupabaseNode().execute(
        _ctx_for(node, resolver=_resolver(project_url="abcd.supabase.co")),
        [Item()],
    )
    assert route.called


def test_project_url_from_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'project_url' is required"):
        project_url_from("   ")


# --- errors / credentials ----------------------------------------------


@respx.mock
async def test_api_error_surfaces_message_and_details() -> None:
    respx.get(f"{_BASE}/posts").mock(
        return_value=Response(
            400,
            json={"message": "bad filter", "details": "operator unknown"},
        ),
    )
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={"operation": "select", "table": "posts"},
        credentials={"supabase_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="bad filter: operator unknown"):
        await SupabaseNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Supabase",
        type="weftlyflow.supabase",
        parameters={"operation": "select", "table": "posts"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await SupabaseNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- direct builder unit tests -----------------------------------------


def test_build_select_caps_limit_at_max() -> None:
    _, _, _, query = build_request(
        "select", {"table": "posts", "limit": 9_999},
    )
    assert query["limit"] == 1000


def test_build_insert_rejects_empty_rows() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_request("insert", {"table": "posts", "rows": []})


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("truncate", {})
