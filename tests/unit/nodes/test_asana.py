"""Unit tests for :class:`AsanaNode`.

Exercises every supported operation against a respx-mocked Asana v1.0
API. Verifies the Bearer auth, the distinctive credential-owned
``Asana-Enable`` opt-in header (propagated automatically, omitted when
empty), the mandatory ``data`` envelope on create/update/comment
bodies, the PUT verb Asana uses for task updates, the paged
list filter validation, and the ``errors[0].message`` envelope parse.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import AsanaApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.asana import AsanaNode
from weftlyflow.nodes.integrations.asana.operations import build_request

_CRED_ID: str = "cr_asana"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "asana-token"
_BASE: str = "https://app.asana.com/api/1.0"


def _resolver(*, enable_flags: str = "") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.asana_api": AsanaApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.asana_api",
                {"access_token": _TOKEN, "enable_flags": enable_flags},
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


# --- list_tasks ------------------------------------------------------


@respx.mock
async def test_list_tasks_with_project_and_limit() -> None:
    route = respx.get(f"{_BASE}/tasks").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={
            "operation": "list_tasks",
            "project": "gid-proj",
            "limit": 25,
            "opt_fields": "name,completed",
        },
        credentials={"asana_api": _CRED_ID},
    )
    await AsanaNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert "Asana-Enable" not in request.headers
    assert request.url.params.get("project") == "gid-proj"
    assert request.url.params.get("limit") == "25"
    assert request.url.params.get("opt_fields") == "name,completed"


def test_list_tasks_requires_project_or_assignee_workspace() -> None:
    with pytest.raises(ValueError, match="requires 'project'"):
        build_request("list_tasks", {})


def test_list_tasks_accepts_assignee_plus_workspace() -> None:
    _, _, _, query = build_request(
        "list_tasks",
        {"assignee": "me", "workspace": "w1"},
    )
    assert query["assignee"] == "me"
    assert query["workspace"] == "w1"


def test_limit_caps_at_max() -> None:
    _, _, _, query = build_request(
        "list_tasks", {"project": "p", "limit": 10_000},
    )
    assert query["limit"] == 100


# --- Asana-Enable header propagation --------------------------------


@respx.mock
async def test_enable_flags_header_propagated_from_credential() -> None:
    route = respx.get(f"{_BASE}/tasks").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={"operation": "list_tasks", "project": "p"},
        credentials={"asana_api": _CRED_ID},
    )
    await AsanaNode().execute(
        _ctx_for(node, resolver=_resolver(
            enable_flags="new_user_task_lists, new_project_templates",
        )),
        [Item()],
    )
    request = route.calls.last.request
    assert (
        request.headers["Asana-Enable"]
        == "new_user_task_lists,new_project_templates"
    )


# --- get_task --------------------------------------------------------


@respx.mock
async def test_get_task_targets_task_path() -> None:
    route = respx.get(f"{_BASE}/tasks/gid-1").mock(
        return_value=Response(200, json={"data": {"gid": "gid-1"}}),
    )
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={
            "operation": "get_task",
            "task_id": "gid-1",
            "opt_fields": "name,notes",
        },
        credentials={"asana_api": _CRED_ID},
    )
    await AsanaNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params.get("opt_fields") == "name,notes"


# --- create_task -----------------------------------------------------


@respx.mock
async def test_create_task_wraps_body_in_data_envelope() -> None:
    route = respx.post(f"{_BASE}/tasks").mock(
        return_value=Response(201, json={"data": {"gid": "new"}}),
    )
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={
            "operation": "create_task",
            "document": {
                "name": "Ship tranche",
                "projects": ["gid-proj"],
            },
        },
        credentials={"asana_api": _CRED_ID},
    )
    await AsanaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"data": {"name": "Ship tranche", "projects": ["gid-proj"]}}


def test_create_task_requires_name() -> None:
    with pytest.raises(ValueError, match=r"'document\.name'"):
        build_request("create_task", {"document": {"notes": "x"}})


# --- update_task (PUT) -----------------------------------------------


@respx.mock
async def test_update_task_uses_put_verb() -> None:
    route = respx.put(f"{_BASE}/tasks/gid-1").mock(return_value=Response(200))
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={
            "operation": "update_task",
            "task_id": "gid-1",
            "document": {"completed": True},
        },
        credentials={"asana_api": _CRED_ID},
    )
    await AsanaNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "PUT"


# --- delete_task -----------------------------------------------------


@respx.mock
async def test_delete_task_sends_delete_verb() -> None:
    route = respx.delete(f"{_BASE}/tasks/gid-1").mock(return_value=Response(200))
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={"operation": "delete_task", "task_id": "gid-1"},
        credentials={"asana_api": _CRED_ID},
    )
    await AsanaNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- add_comment -----------------------------------------------------


@respx.mock
async def test_add_comment_posts_to_stories() -> None:
    route = respx.post(f"{_BASE}/tasks/gid-1/stories").mock(
        return_value=Response(201, json={"data": {"gid": "story-1"}}),
    )
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={
            "operation": "add_comment",
            "task_id": "gid-1",
            "text": "Looks good",
        },
        credentials={"asana_api": _CRED_ID},
    )
    await AsanaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"data": {"text": "Looks good"}}


def test_add_comment_html_takes_precedence() -> None:
    _, _, body, _ = build_request(
        "add_comment",
        {"task_id": "1", "text": "plain", "html_text": "<b>rich</b>"},
    )
    assert body == {"data": {"html_text": "<b>rich</b>"}}


def test_add_comment_requires_text_or_html() -> None:
    with pytest.raises(ValueError, match="'text' or 'html_text'"):
        build_request("add_comment", {"task_id": "1"})


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_errors_envelope() -> None:
    respx.get(f"{_BASE}/tasks/bad").mock(
        return_value=Response(
            404,
            json={"errors": [{"message": "Not found", "help": "Check the GID"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={"operation": "get_task", "task_id": "bad"},
        credentials={"asana_api": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError, match=r"Not found \(Check the GID\)",
    ):
        await AsanaNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Asana",
        type="weftlyflow.asana",
        parameters={"operation": "list_tasks", "project": "p"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AsanaNode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
