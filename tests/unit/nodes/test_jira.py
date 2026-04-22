"""Unit tests for :class:`JiraNode`.

Exercises every supported operation against a respx-mocked Jira Cloud
v3 REST API. Verifies HTTP Basic auth from ``email:api_token``, the
per-tenant base URL composed from the credential's ``site``, and
Atlassian Document Format on ``add_comment``.
"""

from __future__ import annotations

import base64
import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import JiraCloudCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.jira import JiraNode
from weftlyflow.nodes.integrations.jira.operations import build_request

_CRED_ID: str = "cr_jira"
_PROJECT_ID: str = "pr_test"
_SITE: str = "acme"
_BASE: str = f"https://{_SITE}.atlassian.net/rest/api/3"


def _resolver(
    *,
    site: str = _SITE,
    email: str = "eng@acme.io",
    api_token: str = "atk_abc",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.jira_cloud": JiraCloudCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.jira_cloud",
                {"site": site, "email": email, "api_token": api_token},
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


def _expected_basic(email: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode("ascii")


# --- get_issue -----------------------------------------------------------


@respx.mock
async def test_get_issue_uses_basic_auth_with_site_host() -> None:
    route = respx.get(f"{_BASE}/issue/PROJ-1").mock(
        return_value=Response(200, json={"key": "PROJ-1"}),
    )
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={"operation": "get_issue", "issue_key": "PROJ-1"},
        credentials={"jira_cloud": _CRED_ID},
    )
    out = await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["key"] == "PROJ-1"
    request = route.calls.last.request
    assert request.headers["authorization"] == _expected_basic("eng@acme.io", "atk_abc")


@respx.mock
async def test_get_issue_forwards_fields_and_expand_as_csv() -> None:
    route = respx.get(f"{_BASE}/issue/PROJ-1").mock(
        return_value=Response(200, json={"key": "PROJ-1"}),
    )
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={
            "operation": "get_issue",
            "issue_key": "PROJ-1",
            "fields": ["summary", "status"],
            "expand": "renderedFields,changelog",
        },
        credentials={"jira_cloud": _CRED_ID},
    )
    await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    query = dict(route.calls.last.request.url.params)
    assert query["fields"] == "summary,status"
    assert query["expand"] == "renderedFields,changelog"


# --- create_issue --------------------------------------------------------


@respx.mock
async def test_create_issue_wraps_payload_in_fields_envelope() -> None:
    route = respx.post(f"{_BASE}/issue").mock(
        return_value=Response(201, json={"key": "PROJ-99"}),
    )
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={
            "operation": "create_issue",
            "project_key": "PROJ",
            "summary": "Broken login",
            "issue_type": "Bug",
            "extra_fields": {"priority": {"name": "High"}},
        },
        credentials={"jira_cloud": _CRED_ID},
    )
    await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "fields": {
            "project": {"key": "PROJ"},
            "summary": "Broken login",
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
        },
    }


# --- update / delete -----------------------------------------------------


@respx.mock
async def test_update_issue_puts_fields_envelope() -> None:
    route = respx.put(f"{_BASE}/issue/PROJ-1").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={
            "operation": "update_issue",
            "issue_key": "PROJ-1",
            "fields": {"summary": "Fixed title"},
        },
        credentials={"jira_cloud": _CRED_ID},
    )
    await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"fields": {"summary": "Fixed title"}}


@respx.mock
async def test_delete_issue_forwards_subtasks_flag() -> None:
    route = respx.delete(f"{_BASE}/issue/PROJ-1").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={
            "operation": "delete_issue",
            "issue_key": "PROJ-1",
            "delete_subtasks": True,
        },
        credentials={"jira_cloud": _CRED_ID},
    )
    await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    query = dict(route.calls.last.request.url.params)
    assert query["deleteSubtasks"] == "true"


# --- search_issues -------------------------------------------------------


@respx.mock
async def test_search_issues_surfaces_issues_convenience_key() -> None:
    route = respx.post(f"{_BASE}/search").mock(
        return_value=Response(
            200, json={"total": 2, "issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={
            "operation": "search_issues",
            "jql": "project = PROJ",
            "max_results": 25,
            "fields": "summary,status",
        },
        credentials={"jira_cloud": _CRED_ID},
    )
    out = await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [i["key"] for i in result.json["issues"]] == ["PROJ-1", "PROJ-2"]
    body = json.loads(route.calls.last.request.content)
    assert body["jql"] == "project = PROJ"
    assert body["maxResults"] == 25
    assert body["fields"] == ["summary", "status"]


@respx.mock
async def test_search_issues_caps_max_results_at_100() -> None:
    route = respx.post(f"{_BASE}/search").mock(return_value=Response(200, json={}))
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={
            "operation": "search_issues",
            "jql": "project = PROJ",
            "max_results": 9999,
        },
        credentials={"jira_cloud": _CRED_ID},
    )
    await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["maxResults"] == 100


# --- add_comment (ADF) ---------------------------------------------------


@respx.mock
async def test_add_comment_wraps_body_in_adf_document() -> None:
    route = respx.post(f"{_BASE}/issue/PROJ-1/comment").mock(
        return_value=Response(201, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={
            "operation": "add_comment",
            "issue_key": "PROJ-1",
            "body": "LGTM",
        },
        credentials={"jira_cloud": _CRED_ID},
    )
    await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    payload = json.loads(route.calls.last.request.content)
    assert payload["body"]["type"] == "doc"
    assert payload["body"]["version"] == 1
    [para] = payload["body"]["content"]
    assert para["type"] == "paragraph"
    assert para["content"] == [{"type": "text", "text": "LGTM"}]


# --- error paths ---------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_error_messages_array() -> None:
    respx.get(f"{_BASE}/issue/PROJ-missing").mock(
        return_value=Response(
            404,
            json={"errorMessages": ["Issue does not exist."], "errors": {}},
        ),
    )
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={"operation": "get_issue", "issue_key": "PROJ-missing"},
        credentials={"jira_cloud": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Issue does not exist"):
        await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={"operation": "get_issue", "issue_key": "PROJ-1"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await JiraNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_credential_fields_raise() -> None:
    node = Node(
        id="node_1",
        name="Jira",
        type="weftlyflow.jira",
        parameters={"operation": "get_issue", "issue_key": "PROJ-1"},
        credentials={"jira_cloud": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'site', 'email', and 'api_token'"):
        await JiraNode().execute(
            _ctx_for(node, resolver=_resolver(api_token="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_create_requires_project_key() -> None:
    with pytest.raises(ValueError, match="'project_key' is required"):
        build_request("create_issue", {"summary": "x", "issue_type": "Task"})


def test_build_request_update_requires_fields() -> None:
    with pytest.raises(ValueError, match="'fields'"):
        build_request("update_issue", {"issue_key": "PROJ-1"})


def test_build_request_add_comment_requires_body() -> None:
    with pytest.raises(ValueError, match="'body' is required"):
        build_request("add_comment", {"issue_key": "PROJ-1", "body": "  "})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("archive_issue", {})
