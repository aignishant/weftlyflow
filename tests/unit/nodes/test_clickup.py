"""Unit tests for :class:`ClickUpNode`.

Exercises every supported operation against a respx-mocked ClickUp v2
REST API. Verifies the **unprefixed** ``Authorization`` header (neither
``Bearer`` nor ``Bot``), the ``statuses[]`` repeated query parameter on
``list_tasks``, and the update-field whitelist.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlparse

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ClickUpApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.clickup import ClickUpNode
from weftlyflow.nodes.integrations.clickup.operations import build_request

_CRED_ID: str = "cr_cu"
_PROJECT_ID: str = "pr_test"
_BASE: str = "https://api.clickup.com/api/v2"


def _resolver(*, api_token: str = "pk_abc") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.clickup_api": ClickUpApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.clickup_api",
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


# --- create_task ---------------------------------------------------------


@respx.mock
async def test_create_task_uses_unprefixed_authorization_header() -> None:
    route = respx.post(f"{_BASE}/list/abc/task").mock(
        return_value=Response(200, json={"id": "t1"}),
    )
    node = Node(
        id="node_1",
        name="ClickUp",
        type="weftlyflow.clickup",
        parameters={
            "operation": "create_task",
            "list_id": "abc",
            "name": "Buy milk",
            "description": "2%",
            "priority": 2,
            "assignees": [1, 2],
            "status": "open",
            "extra_fields": {"due_date": 1700000000},
        },
        credentials={"clickup_api": _CRED_ID},
    )
    await ClickUpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["authorization"] == "pk_abc"
    assert not request.headers["authorization"].lower().startswith("bearer")
    assert not request.headers["authorization"].lower().startswith("bot")
    body = json.loads(request.content)
    assert body == {
        "name": "Buy milk",
        "description": "2%",
        "assignees": [1, 2],
        "status": "open",
        "priority": 2,
        "due_date": 1700000000,
    }


# --- get / update / delete ----------------------------------------------


@respx.mock
async def test_get_task_hits_task_path() -> None:
    route = respx.get(f"{_BASE}/task/t1").mock(
        return_value=Response(200, json={"id": "t1"}),
    )
    node = Node(
        id="node_1",
        name="ClickUp",
        type="weftlyflow.clickup",
        parameters={"operation": "get_task", "task_id": "t1"},
        credentials={"clickup_api": _CRED_ID},
    )
    await ClickUpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


@respx.mock
async def test_update_task_puts_allowed_fields() -> None:
    route = respx.put(f"{_BASE}/task/t1").mock(return_value=Response(200, json={}))
    node = Node(
        id="node_1",
        name="ClickUp",
        type="weftlyflow.clickup",
        parameters={
            "operation": "update_task",
            "task_id": "t1",
            "fields": {"name": "Renamed", "priority": 3},
        },
        credentials={"clickup_api": _CRED_ID},
    )
    await ClickUpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "Renamed", "priority": 3}


@respx.mock
async def test_delete_task_issues_delete() -> None:
    route = respx.delete(f"{_BASE}/task/t1").mock(return_value=Response(200, json={}))
    node = Node(
        id="node_1",
        name="ClickUp",
        type="weftlyflow.clickup",
        parameters={"operation": "delete_task", "task_id": "t1"},
        credentials={"clickup_api": _CRED_ID},
    )
    out = await ClickUpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["status"] == 200
    assert route.called


# --- list_tasks ---------------------------------------------------------


@respx.mock
async def test_list_tasks_emits_repeated_statuses_query_param() -> None:
    route = respx.get(f"{_BASE}/list/abc/task").mock(
        return_value=Response(200, json={"tasks": [{"id": "t1"}]}),
    )
    node = Node(
        id="node_1",
        name="ClickUp",
        type="weftlyflow.clickup",
        parameters={
            "operation": "list_tasks",
            "list_id": "abc",
            "archived": False,
            "page": 2,
            "subtasks": True,
            "statuses": "open, in progress",
            "order_by": "due_date",
        },
        credentials={"clickup_api": _CRED_ID},
    )
    out = await ClickUpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [t["id"] for t in result.json["tasks"]] == ["t1"]
    url = urlparse(str(route.calls.last.request.url))
    pairs = parse_qsl(url.query, keep_blank_values=True)
    status_values = [v for k, v in pairs if k == "statuses[]"]
    assert status_values == ["open", "in progress"]
    flat = dict(pairs)
    assert flat["archived"] == "false"
    assert flat["subtasks"] == "true"
    assert flat["page"] == "2"
    assert flat["order_by"] == "due_date"


# --- error & credential paths -------------------------------------------


@respx.mock
async def test_api_error_surfaces_err_message() -> None:
    respx.post(f"{_BASE}/list/abc/task").mock(
        return_value=Response(400, json={"err": "List not found", "ECODE": "LIST_004"}),
    )
    node = Node(
        id="node_1",
        name="ClickUp",
        type="weftlyflow.clickup",
        parameters={"operation": "create_task", "list_id": "abc", "name": "x"},
        credentials={"clickup_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="List not found"):
        await ClickUpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="ClickUp",
        type="weftlyflow.clickup",
        parameters={"operation": "get_task", "task_id": "t1"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await ClickUpNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_token_raises() -> None:
    node = Node(
        id="node_1",
        name="ClickUp",
        type="weftlyflow.clickup",
        parameters={"operation": "get_task", "task_id": "t1"},
        credentials={"clickup_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_token'"):
        await ClickUpNode().execute(
            _ctx_for(node, resolver=_resolver(api_token="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_create_requires_name() -> None:
    with pytest.raises(ValueError, match="'name' is required"):
        build_request("create_task", {"list_id": "abc"})


def test_build_request_update_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown task field"):
        build_request(
            "update_task",
            {"task_id": "t1", "fields": {"name": "ok", "surprise": 1}},
        )


def test_build_request_create_rejects_priority_out_of_range() -> None:
    with pytest.raises(ValueError, match=r"1\.\.4"):
        build_request(
            "create_task",
            {"list_id": "abc", "name": "x", "priority": 9},
        )


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("snooze_task", {})
