"""Unit tests for :class:`MondayNode`.

Exercises every supported GraphQL operation against a respx-mocked
Monday.com endpoint. Verifies the raw ``Authorization`` header (no
``Bearer`` prefix), that every request posts to the single ``/v2``
endpoint, and that ``column_values`` is JSON-encoded before the wire.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import MondayApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.monday import MondayNode
from weftlyflow.nodes.integrations.monday.operations import build_request

_CRED_ID: str = "cr_mon"
_PROJECT_ID: str = "pr_test"
_API_URL: str = "https://api.monday.com/v2"


def _resolver(*, api_token: str = "mon_tok") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.monday_api": MondayApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.monday_api",
                {"api_token": api_token},
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


# --- get_boards / get_board ---------------------------------------------


@respx.mock
async def test_get_boards_posts_query_with_raw_auth_header() -> None:
    route = respx.post(_API_URL).mock(
        return_value=Response(200, json={"data": {"boards": [{"id": "1"}]}}),
    )
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={"operation": "get_boards", "limit": 10},
        credentials={"monday_api": _CRED_ID},
    )
    out = await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["operation"] == "get_boards"
    request = route.calls.last.request
    assert request.headers["authorization"] == "mon_tok"
    assert request.headers["content-type"] == "application/json"
    body = json.loads(request.content)
    assert "boards(limit: $limit)" in body["query"]
    assert body["variables"] == {"limit": 10}


@respx.mock
async def test_get_board_wraps_id_in_list() -> None:
    route = respx.post(_API_URL).mock(
        return_value=Response(200, json={"data": {"boards": []}}),
    )
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={"operation": "get_board", "board_id": "12345"},
        credentials={"monday_api": _CRED_ID},
    )
    await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["variables"] == {"id": ["12345"]}


# --- get_items / limit capping ------------------------------------------


@respx.mock
async def test_get_items_caps_limit_at_500() -> None:
    route = respx.post(_API_URL).mock(
        return_value=Response(200, json={"data": {"boards": []}}),
    )
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={
            "operation": "get_items",
            "board_id": "99",
            "limit": 99_999,
        },
        credentials={"monday_api": _CRED_ID},
    )
    await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["variables"] == {"board_id": "99", "limit": 500}


# --- create_item --------------------------------------------------------


@respx.mock
async def test_create_item_json_encodes_column_values() -> None:
    route = respx.post(_API_URL).mock(
        return_value=Response(200, json={"data": {"create_item": {"id": "5"}}}),
    )
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={
            "operation": "create_item",
            "board_id": "10",
            "item_name": "Ship it",
            "column_values": {"status": {"label": "Done"}},
            "group_id": "topics",
        },
        credentials={"monday_api": _CRED_ID},
    )
    await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    variables = body["variables"]
    assert variables["board_id"] == "10"
    assert variables["item_name"] == "Ship it"
    assert variables["group_id"] == "topics"
    assert json.loads(variables["column_values"]) == {"status": {"label": "Done"}}


@respx.mock
async def test_create_item_allows_omitted_column_values() -> None:
    route = respx.post(_API_URL).mock(
        return_value=Response(200, json={"data": {"create_item": {"id": "5"}}}),
    )
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={
            "operation": "create_item",
            "board_id": "10",
            "item_name": "Just a name",
        },
        credentials={"monday_api": _CRED_ID},
    )
    await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    variables = body["variables"]
    assert variables["column_values"] is None
    assert variables["group_id"] is None


# --- change_column_values -----------------------------------------------


@respx.mock
async def test_change_column_values_requires_non_empty_object() -> None:
    respx.post(_API_URL).mock(return_value=Response(200, json={"data": {}}))
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={
            "operation": "change_column_values",
            "board_id": "1",
            "item_id": "2",
            "column_values": {},
        },
        credentials={"monday_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="column_values"):
        await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_change_column_values_posts_encoded_json() -> None:
    route = respx.post(_API_URL).mock(
        return_value=Response(
            200,
            json={"data": {"change_multiple_column_values": {"id": "2"}}},
        ),
    )
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={
            "operation": "change_column_values",
            "board_id": "1",
            "item_id": "2",
            "column_values": {"priority": {"label": "High"}},
        },
        credentials={"monday_api": _CRED_ID},
    )
    await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert json.loads(body["variables"]["column_values"]) == {
        "priority": {"label": "High"},
    }


# --- create_update ------------------------------------------------------


@respx.mock
async def test_create_update_requires_non_empty_body() -> None:
    respx.post(_API_URL).mock(return_value=Response(200, json={"data": {}}))
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={
            "operation": "create_update",
            "item_id": "2",
            "body": "   ",
        },
        credentials={"monday_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'body'"):
        await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- error handling -----------------------------------------------------


@respx.mock
async def test_http_error_surfaces_graphql_message() -> None:
    respx.post(_API_URL).mock(
        return_value=Response(400, json={"errors": [{"message": "Bad query"}]}),
    )
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={"operation": "get_boards"},
        credentials={"monday_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Bad query"):
        await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_200_with_errors_array_raises() -> None:
    respx.post(_API_URL).mock(
        return_value=Response(
            200, json={"errors": [{"message": "permission denied"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={"operation": "get_boards"},
        credentials={"monday_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="permission denied"):
        await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={"operation": "get_boards"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MondayNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_token_raises() -> None:
    node = Node(
        id="node_1",
        name="Monday",
        type="weftlyflow.monday",
        parameters={"operation": "get_boards"},
        credentials={"monday_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_token'"):
        await MondayNode().execute(
            _ctx_for(node, resolver=_resolver(api_token="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_item", {})


def test_build_request_create_item_requires_board_id() -> None:
    with pytest.raises(ValueError, match="'board_id'"):
        build_request("create_item", {"item_name": "x"})


def test_build_request_create_item_rejects_non_dict_columns() -> None:
    with pytest.raises(ValueError, match="'column_values'"):
        build_request(
            "create_item",
            {"board_id": "1", "item_name": "x", "column_values": "oops"},
        )
