"""Unit tests for :class:`NotionNode`.

Exercises every supported operation against a respx-mocked Notion REST
API. Checks that the required ``Notion-Version`` header is always attached.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import NotionApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.notion import NotionNode
from weftlyflow.nodes.integrations.notion.operations import build_request

_CRED_ID: str = "cr_notion"
_PROJECT_ID: str = "pr_test"
_DEFAULT_VERSION: str = "2022-06-28"


def _resolver(
    *,
    access_token: str = "secret_abc",
    notion_version: str = "",
) -> InMemoryCredentialResolver:
    payload: dict[str, object] = {"access_token": access_token}
    if notion_version:
        payload["notion_version"] = notion_version
    return InMemoryCredentialResolver(
        types={"weftlyflow.notion_api": NotionApiCredential},
        rows={_CRED_ID: ("weftlyflow.notion_api", payload, _PROJECT_ID)},
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


# --- query_database --------------------------------------------------------


@respx.mock
async def test_query_database_surfaces_results_array() -> None:
    route = respx.post("https://api.notion.com/v1/databases/db_1/query").mock(
        return_value=Response(
            200,
            json={"results": [{"id": "p1"}, {"id": "p2"}], "has_more": False},
        ),
    )
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={
            "operation": "query_database",
            "database_id": "db_1",
            "filter": {"property": "Status", "status": {"equals": "Open"}},
            "sorts": [{"property": "Created", "direction": "descending"}],
            "page_size": 25,
            "start_cursor": "cur1",
        },
        credentials={"notion_api": _CRED_ID},
    )
    out = await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [r["id"] for r in result.json["results"]] == ["p1", "p2"]
    body = json.loads(route.calls.last.request.content)
    assert body["filter"] == {"property": "Status", "status": {"equals": "Open"}}
    assert body["sorts"] == [{"property": "Created", "direction": "descending"}]
    assert body["page_size"] == 25
    assert body["start_cursor"] == "cur1"
    headers = route.calls.last.request.headers
    assert headers["authorization"] == "Bearer secret_abc"
    assert headers["notion-version"] == _DEFAULT_VERSION


@respx.mock
async def test_query_database_caps_page_size_at_max() -> None:
    route = respx.post("https://api.notion.com/v1/databases/db_1/query").mock(
        return_value=Response(200, json={"results": []}),
    )
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={
            "operation": "query_database",
            "database_id": "db_1",
            "page_size": 9999,
        },
        credentials={"notion_api": _CRED_ID},
    )
    await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["page_size"] == 100


@respx.mock
async def test_query_database_respects_override_notion_version() -> None:
    route = respx.post("https://api.notion.com/v1/databases/db_1/query").mock(
        return_value=Response(200, json={"results": []}),
    )
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={"operation": "query_database", "database_id": "db_1"},
        credentials={"notion_api": _CRED_ID},
    )
    resolver = _resolver(notion_version="2025-01-01")
    await NotionNode().execute(_ctx_for(node, resolver=resolver), [Item()])
    assert route.calls.last.request.headers["notion-version"] == "2025-01-01"


# --- create_page -----------------------------------------------------------


@respx.mock
async def test_create_page_posts_parent_and_properties() -> None:
    route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=Response(200, json={"id": "page_new"}),
    )
    properties = {"Name": {"title": [{"text": {"content": "Hello"}}]}}
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={
            "operation": "create_page",
            "parent_database_id": "db_1",
            "properties": properties,
            "children": [
                {"object": "block", "type": "paragraph", "paragraph": {}},
            ],
        },
        credentials={"notion_api": _CRED_ID},
    )
    out = await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["id"] == "page_new"
    body = json.loads(route.calls.last.request.content)
    assert body["parent"] == {"database_id": "db_1"}
    assert body["properties"] == properties
    assert body["children"][0]["type"] == "paragraph"


@respx.mock
async def test_create_page_accepts_parent_page_id() -> None:
    route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=Response(200, json={"id": "page_new"}),
    )
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={
            "operation": "create_page",
            "parent_page_id": "parent_abc",
            "properties": {"title": []},
        },
        credentials={"notion_api": _CRED_ID},
    )
    await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["parent"] == {"page_id": "parent_abc"}


@respx.mock
async def test_create_page_without_parent_raises() -> None:
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={"operation": "create_page", "properties": {}},
        credentials={"notion_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="parent_database_id"):
        await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_create_page_rejects_non_object_properties() -> None:
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={
            "operation": "create_page",
            "parent_database_id": "db_1",
            "properties": "not-an-object",
        },
        credentials={"notion_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="properties"):
        await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- retrieve_page ---------------------------------------------------------


@respx.mock
async def test_retrieve_page_is_a_get() -> None:
    route = respx.get("https://api.notion.com/v1/pages/page_abc").mock(
        return_value=Response(200, json={"id": "page_abc", "archived": False}),
    )
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={"operation": "retrieve_page", "page_id": "page_abc"},
        credentials={"notion_api": _CRED_ID},
    )
    out = await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["id"] == "page_abc"
    assert route.called


# --- error paths -----------------------------------------------------------


@respx.mock
async def test_api_error_becomes_node_execution_error() -> None:
    respx.get("https://api.notion.com/v1/pages/page_abc").mock(
        return_value=Response(404, json={"message": "page not found"}),
    )
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={"operation": "retrieve_page", "page_id": "page_abc"},
        credentials={"notion_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="page not found"):
        await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={"operation": "retrieve_page", "page_id": "p1"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await NotionNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_access_token_raises() -> None:
    node = Node(
        id="node_1",
        name="Notion",
        type="weftlyflow.notion",
        parameters={"operation": "retrieve_page", "page_id": "p1"},
        credentials={"notion_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'access_token'"):
        await NotionNode().execute(
            _ctx_for(node, resolver=_resolver(access_token="")), [Item()],
        )


# --- direct builder unit tests --------------------------------------------


def test_build_request_query_database_requires_database_id() -> None:
    with pytest.raises(ValueError, match="database_id"):
        build_request("query_database", {})


def test_build_request_retrieve_page_requires_page_id() -> None:
    with pytest.raises(ValueError, match="page_id"):
        build_request("retrieve_page", {})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
