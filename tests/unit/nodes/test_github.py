"""Unit tests for :class:`GitHubNode`.

Exercises every supported operation against a respx-mocked GitHub REST API
so no network is required. One behaviour per test per the AAA convention.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BearerTokenCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.github import GitHubNode
from weftlyflow.nodes.integrations.github.operations import build_request

_CRED_ID: str = "cr_github"
_PROJECT_ID: str = "pr_test"


def _resolver(*, token: str = "ghp_abc") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.bearer_token": BearerTokenCredential},
        rows={_CRED_ID: ("weftlyflow.bearer_token", {"token": token}, _PROJECT_ID)},
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


# --- create_issue ----------------------------------------------------------


@respx.mock
async def test_create_issue_posts_title_and_body() -> None:
    route = respx.post("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=Response(201, json={"number": 42, "title": "hello"}),
    )
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={
            "operation": "create_issue",
            "owner": "acme",
            "repo": "widgets",
            "title": "hello",
            "body": "world",
            "labels": "bug, urgent",
            "assignees": "alice",
        },
        credentials={"github_api": _CRED_ID},
    )
    out = await GitHubNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["status"] == 201
    assert result.json["response"]["number"] == 42
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "title": "hello",
        "body": "world",
        "labels": ["bug", "urgent"],
        "assignees": ["alice"],
    }
    headers = route.calls.last.request.headers
    assert headers["authorization"] == "Bearer ghp_abc"
    assert headers["accept"] == "application/vnd.github+json"
    assert headers["x-github-api-version"] == "2022-11-28"


@respx.mock
async def test_create_issue_without_title_raises() -> None:
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={
            "operation": "create_issue",
            "owner": "acme",
            "repo": "widgets",
        },
        credentials={"github_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="title"):
        await GitHubNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- list_issues -----------------------------------------------------------


@respx.mock
async def test_list_issues_surfaces_issues_array() -> None:
    route = respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[{"number": 1}, {"number": 2}]),
    )
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={
            "operation": "list_issues",
            "owner": "acme",
            "repo": "widgets",
            "state": "closed",
            "labels": "bug",
            "per_page": 50,
            "page": 2,
        },
        credentials={"github_api": _CRED_ID},
    )
    out = await GitHubNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [i["number"] for i in result.json["issues"]] == [1, 2]
    query = dict(route.calls.last.request.url.params)
    assert query["state"] == "closed"
    assert query["labels"] == "bug"
    assert query["per_page"] == "50"
    assert query["page"] == "2"


@respx.mock
async def test_list_issues_caps_per_page_at_max() -> None:
    route = respx.get("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[]),
    )
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={
            "operation": "list_issues",
            "owner": "acme",
            "repo": "widgets",
            "per_page": 9999,
        },
        credentials={"github_api": _CRED_ID},
    )
    await GitHubNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.calls.last.request.url.params["per_page"] == "100"


# --- get_repo / create_comment --------------------------------------------


@respx.mock
async def test_get_repo_is_a_plain_get() -> None:
    route = respx.get("https://api.github.com/repos/acme/widgets").mock(
        return_value=Response(200, json={"name": "widgets", "private": False}),
    )
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={"operation": "get_repo", "owner": "acme", "repo": "widgets"},
        credentials={"github_api": _CRED_ID},
    )
    out = await GitHubNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["name"] == "widgets"
    assert route.called


@respx.mock
async def test_create_comment_posts_body() -> None:
    route = respx.post(
        "https://api.github.com/repos/acme/widgets/issues/42/comments",
    ).mock(return_value=Response(201, json={"id": 99, "body": "thx"}))
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={
            "operation": "create_comment",
            "owner": "acme",
            "repo": "widgets",
            "issue_number": 42,
            "body": "thx",
        },
        credentials={"github_api": _CRED_ID},
    )
    await GitHubNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"body": "thx"}


# --- error paths -----------------------------------------------------------


@respx.mock
async def test_api_error_becomes_node_execution_error() -> None:
    respx.post("https://api.github.com/repos/acme/widgets/issues").mock(
        return_value=Response(422, json={"message": "Validation failed"}),
    )
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={
            "operation": "create_issue",
            "owner": "acme",
            "repo": "widgets",
            "title": "x",
        },
        credentials={"github_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Validation failed"):
        await GitHubNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={
            "operation": "get_repo",
            "owner": "acme",
            "repo": "widgets",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await GitHubNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_token_raises() -> None:
    node = Node(
        id="node_1",
        name="GitHub",
        type="weftlyflow.github",
        parameters={
            "operation": "get_repo",
            "owner": "acme",
            "repo": "widgets",
        },
        credentials={"github_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'token'"):
        await GitHubNode().execute(
            _ctx_for(node, resolver=_resolver(token="")), [Item()],
        )


# --- direct builder unit tests --------------------------------------------


def test_build_request_rejects_unknown_state() -> None:
    with pytest.raises(ValueError, match="invalid issue state"):
        build_request(
            "list_issues",
            {"owner": "a", "repo": "b", "state": "stale"},
        )


def test_build_request_create_comment_requires_body() -> None:
    with pytest.raises(ValueError, match="create_comment requires 'body'"):
        build_request(
            "create_comment",
            {"owner": "a", "repo": "b", "issue_number": 1},
        )


def test_build_request_requires_owner_and_repo() -> None:
    with pytest.raises(ValueError, match="'owner' and 'repo' are required"):
        build_request("get_repo", {})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
