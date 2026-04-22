"""Unit tests for :class:`LinearNode`.

Exercises every supported operation against the respx-mocked Linear
GraphQL endpoint. Verifies the distinctive unprefixed
``Authorization: <api_key>`` header (no Bearer), the single-endpoint
POST-only surface, the GraphQL body shape
(``{query, variables, operationName}``), the cursor-paginated
variables, and the GraphQL ``errors[0].message`` surfacing.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import LinearApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.linear import LinearNode
from weftlyflow.nodes.integrations.linear.constants import API_URL
from weftlyflow.nodes.integrations.linear.operations import build_request

_CRED_ID: str = "cr_linear"
_PROJECT_ID: str = "pr_test"
_API_KEY: str = "lin-secret"


def _resolver(*, api_key: str = _API_KEY) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.linear_api": LinearApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.linear_api",
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


# --- list_issues -------------------------------------------------------


@respx.mock
async def test_list_issues_uses_raw_authorization_without_bearer() -> None:
    route = respx.post(API_URL).mock(
        return_value=Response(200, json={"data": {"issues": {"nodes": []}}}),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={
            "operation": "list_issues",
            "first": 25,
            "filter": {"state": {"type": {"eq": "started"}}},
        },
        credentials={"linear_api": _CRED_ID},
    )
    await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == _API_KEY
    assert not request.headers["Authorization"].startswith("Bearer")
    body = json.loads(request.content)
    assert body["operationName"] == "ListIssues"
    assert "query ListIssues" in body["query"]
    assert body["variables"] == {
        "first": 25,
        "filter": {"state": {"type": {"eq": "started"}}},
    }


@respx.mock
async def test_list_issues_passes_cursor_in_variables() -> None:
    route = respx.post(API_URL).mock(
        return_value=Response(200, json={"data": {"issues": {"nodes": []}}}),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={"operation": "list_issues", "after": "cur_abc"},
        credentials={"linear_api": _CRED_ID},
    )
    await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["variables"]["after"] == "cur_abc"


# --- get_issue ---------------------------------------------------------


@respx.mock
async def test_get_issue_sends_id_variable() -> None:
    route = respx.post(API_URL).mock(
        return_value=Response(200, json={"data": {"issue": {"id": "iss_1"}}}),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={"operation": "get_issue", "issue_id": "iss_1"},
        credentials={"linear_api": _CRED_ID},
    )
    await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["operationName"] == "GetIssue"
    assert body["variables"] == {"id": "iss_1"}


# --- create_issue ------------------------------------------------------


@respx.mock
async def test_create_issue_wraps_fields_in_input_payload() -> None:
    route = respx.post(API_URL).mock(
        return_value=Response(
            200,
            json={"data": {"issueCreate": {"success": True, "issue": {"id": "i1"}}}},
        ),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={
            "operation": "create_issue",
            "team_id": "team_engineering",
            "title": "Fix the thing",
            "description": "Detailed repro steps here.",
            "extra": {"priority": 2, "labelIds": ["lbl_bug"]},
        },
        credentials={"linear_api": _CRED_ID},
    )
    await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["operationName"] == "CreateIssue"
    assert body["variables"] == {
        "input": {
            "teamId": "team_engineering",
            "title": "Fix the thing",
            "description": "Detailed repro steps here.",
            "priority": 2,
            "labelIds": ["lbl_bug"],
        },
    }


def test_create_issue_rejects_unknown_extra_field() -> None:
    with pytest.raises(ValueError, match="unknown issue input field"):
        build_request(
            "create_issue",
            {"team_id": "t", "title": "x", "extra": {"bogus": 1}},
        )


# --- update_issue ------------------------------------------------------


@respx.mock
async def test_update_issue_sends_id_and_input() -> None:
    route = respx.post(API_URL).mock(
        return_value=Response(
            200,
            json={"data": {"issueUpdate": {"success": True, "issue": {"id": "i1"}}}},
        ),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={
            "operation": "update_issue",
            "issue_id": "i1",
            "fields": {"stateId": "st_done", "priority": 3},
        },
        credentials={"linear_api": _CRED_ID},
    )
    await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["operationName"] == "UpdateIssue"
    assert body["variables"] == {
        "id": "i1",
        "input": {"stateId": "st_done", "priority": 3},
    }


def test_update_issue_rejects_empty_fields() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_request("update_issue", {"issue_id": "i1", "fields": {}})


# --- list_teams / list_projects ----------------------------------------


@respx.mock
async def test_list_teams_uses_teams_query() -> None:
    route = respx.post(API_URL).mock(
        return_value=Response(200, json={"data": {"teams": {"nodes": []}}}),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={"operation": "list_teams", "first": 10},
        credentials={"linear_api": _CRED_ID},
    )
    await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["operationName"] == "ListTeams"
    assert body["variables"] == {"first": 10}


@respx.mock
async def test_list_projects_uses_projects_query() -> None:
    route = respx.post(API_URL).mock(
        return_value=Response(200, json={"data": {"projects": {"nodes": []}}}),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={"operation": "list_projects"},
        credentials={"linear_api": _CRED_ID},
    )
    await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["operationName"] == "ListProjects"


# --- errors / credentials ----------------------------------------------


@respx.mock
async def test_graphql_error_surfaces_as_node_execution_error() -> None:
    respx.post(API_URL).mock(
        return_value=Response(
            200,
            json={"errors": [{"message": "invalid team id"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={
            "operation": "create_issue",
            "team_id": "bogus",
            "title": "x",
        },
        credentials={"linear_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid team id"):
        await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_http_error_surfaces_status_message() -> None:
    respx.post(API_URL).mock(
        return_value=Response(401, json={"errors": [{"message": "unauthorized"}]}),
    )
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={"operation": "list_issues"},
        credentials={"linear_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unauthorized"):
        await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Linear",
        type="weftlyflow.linear",
        parameters={"operation": "list_issues"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await LinearNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- direct builder unit tests -----------------------------------------


def test_build_list_caps_first_at_max() -> None:
    _, _, variables = build_request("list_issues", {"first": 9_999})
    assert variables["first"] == 250


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_everything", {})
