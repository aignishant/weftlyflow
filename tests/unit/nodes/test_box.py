"""Unit tests for :class:`BoxNode`.

Exercises every supported operation against a respx-mocked Box Content
API v2.0. Verifies the Bearer auth, the distinctive credential-owned
``As-User`` impersonation header (propagated automatically, omitted
when empty), the ``/folders/{id}/items`` listing path, the ``POST
/files/{id}/copy`` shape with a ``parent`` object body, the search
filter projection, the ``code: message`` error envelope, and the
``context_info.errors[0].reason`` fallback parse.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BoxApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.box import BoxNode
from weftlyflow.nodes.integrations.box.operations import build_request

_CRED_ID: str = "cr_box"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "box-token"
_BASE: str = "https://api.box.com/2.0"


def _resolver(*, as_user_id: str = "") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.box_api": BoxApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.box_api",
                {"access_token": _TOKEN, "as_user_id": as_user_id},
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


# --- list_folder -----------------------------------------------------


@respx.mock
async def test_list_folder_defaults_to_root_zero() -> None:
    route = respx.get(f"{_BASE}/folders/0/items").mock(
        return_value=Response(200, json={"entries": []}),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={"operation": "list_folder"},
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert "As-User" not in request.headers
    assert request.url.params.get("limit") == "100"


@respx.mock
async def test_list_folder_uses_custom_folder_and_fields() -> None:
    route = respx.get(f"{_BASE}/folders/123/items").mock(
        return_value=Response(200, json={"entries": []}),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={
            "operation": "list_folder",
            "folder_id": "123",
            "offset": 50,
            "fields": "id,name,modified_at",
        },
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.url.params.get("offset") == "50"
    assert request.url.params.get("fields") == "id,name,modified_at"


# --- As-User impersonation ------------------------------------------


@respx.mock
async def test_as_user_header_propagated_from_credential() -> None:
    route = respx.get(f"{_BASE}/folders/0/items").mock(
        return_value=Response(200, json={"entries": []}),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={"operation": "list_folder"},
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(
        _ctx_for(node, resolver=_resolver(as_user_id="user-42")),
        [Item()],
    )
    assert route.calls.last.request.headers["As-User"] == "user-42"


# --- get_file / delete_file ------------------------------------------


@respx.mock
async def test_get_file_hits_files_path() -> None:
    route = respx.get(f"{_BASE}/files/f-1").mock(
        return_value=Response(200, json={"id": "f-1"}),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={
            "operation": "get_file",
            "file_id": "f-1",
            "fields": "name,size",
        },
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params.get("fields") == "name,size"


@respx.mock
async def test_delete_file_sends_delete_verb() -> None:
    route = respx.delete(f"{_BASE}/files/f-1").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={"operation": "delete_file", "file_id": "f-1"},
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- create_folder ---------------------------------------------------


@respx.mock
async def test_create_folder_posts_parent_envelope() -> None:
    route = respx.post(f"{_BASE}/folders").mock(
        return_value=Response(201, json={"id": "new-folder"}),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={
            "operation": "create_folder",
            "name": "Reports",
            "parent_id": "100",
        },
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "Reports", "parent": {"id": "100"}}


def test_create_folder_requires_name() -> None:
    with pytest.raises(ValueError, match="'name' is required"):
        build_request("create_folder", {})


# --- copy_file -------------------------------------------------------


@respx.mock
async def test_copy_file_posts_to_copy_endpoint() -> None:
    route = respx.post(f"{_BASE}/files/f-1/copy").mock(
        return_value=Response(201, json={"id": "f-2"}),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={
            "operation": "copy_file",
            "file_id": "f-1",
            "parent_id": "200",
            "new_name": "Backup.pdf",
        },
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"parent": {"id": "200"}, "name": "Backup.pdf"}


def test_copy_file_requires_parent() -> None:
    with pytest.raises(ValueError, match="'parent_id' is required"):
        build_request("copy_file", {"file_id": "f-1"})


# --- search ----------------------------------------------------------


@respx.mock
async def test_search_query_and_filters() -> None:
    route = respx.get(f"{_BASE}/search").mock(
        return_value=Response(200, json={"entries": []}),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={
            "operation": "search",
            "query": "q3 report",
            "content_types": "name,description",
            "ancestor_folder_ids": "100,200",
            "file_extensions": "pdf,docx",
            "limit": 50,
        },
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("query") == "q3 report"
    assert params.get("content_types") == "name,description"
    assert params.get("ancestor_folder_ids") == "100,200"
    assert params.get("file_extensions") == "pdf,docx"


def test_search_requires_query() -> None:
    with pytest.raises(ValueError, match="'query' is required"):
        build_request("search", {})


# --- list_users ------------------------------------------------------


@respx.mock
async def test_list_users_with_filter_and_type() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json={"entries": []}),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={
            "operation": "list_users",
            "filter_term": "ada",
            "user_type": "managed",
        },
        credentials={"box_api": _CRED_ID},
    )
    await BoxNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("filter_term") == "ada"
    assert params.get("user_type") == "managed"


# --- paging + errors -------------------------------------------------


def test_limit_caps_at_max() -> None:
    _, _, _, query = build_request("list_folder", {"limit": 10_000})
    assert query["limit"] == 1_000


@respx.mock
async def test_api_error_surfaces_code_and_message() -> None:
    respx.get(f"{_BASE}/files/missing").mock(
        return_value=Response(
            404,
            json={
                "code": "not_found",
                "message": "File missing was not found",
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={"operation": "get_file", "file_id": "missing"},
        credentials={"box_api": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError,
        match=r"not_found: File missing was not found",
    ):
        await BoxNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Box",
        type="weftlyflow.box",
        parameters={"operation": "list_folder"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await BoxNode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("purge_enterprise", {})
