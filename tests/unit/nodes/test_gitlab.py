"""Unit tests for :class:`GitLabNode`.

Exercises every supported operation against a respx-mocked GitLab v4
REST API. Verifies the ``PRIVATE-TOKEN`` header (no Bearer prefix),
URL-encoded project paths (``group%2Frepo``), and the configurable
``base_url`` for self-hosted instances.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import GitLabTokenCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.gitlab import GitLabNode
from weftlyflow.nodes.integrations.gitlab.operations import build_request

_CRED_ID: str = "cr_gl"
_PROJECT_ID: str = "pr_test"
_PROJECT_PATH: str = "acme/widgets"
_ENCODED_PROJECT: str = "acme%2Fwidgets"


def _resolver(
    *,
    base_url: str = "https://gitlab.com",
    access_token: str = "glpat_abc",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.gitlab_token": GitLabTokenCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.gitlab_token",
                {"base_url": base_url, "access_token": access_token},
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


# --- get_issue -----------------------------------------------------------


@respx.mock
async def test_get_issue_uses_private_token_header_on_gitlab_com() -> None:
    route = respx.get(
        f"https://gitlab.com/api/v4/projects/{_ENCODED_PROJECT}/issues/7",
    ).mock(return_value=Response(200, json={"iid": 7}))
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "get_issue",
            "project_id": _PROJECT_PATH,
            "issue_iid": 7,
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    out = await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["iid"] == 7
    request = route.calls.last.request
    assert request.headers["private-token"] == "glpat_abc"
    assert "authorization" not in request.headers


@respx.mock
async def test_get_issue_uses_self_hosted_base_url() -> None:
    route = respx.get(
        f"https://git.internal.io/api/v4/projects/{_ENCODED_PROJECT}/issues/7",
    ).mock(return_value=Response(200, json={"iid": 7}))
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "get_issue",
            "project_id": _PROJECT_PATH,
            "issue_iid": 7,
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    await GitLabNode().execute(
        _ctx_for(node, resolver=_resolver(base_url="https://git.internal.io/")),
        [Item()],
    )
    assert route.called


# --- create / update / add_comment --------------------------------------


@respx.mock
async def test_create_issue_posts_title_and_joins_labels() -> None:
    route = respx.post(
        f"https://gitlab.com/api/v4/projects/{_ENCODED_PROJECT}/issues",
    ).mock(return_value=Response(201, json={"iid": 42}))
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "create_issue",
            "project_id": _PROJECT_PATH,
            "title": "Something broke",
            "description": "Details",
            "labels": ["bug", "urgent"],
            "assignee_ids": [12, 34],
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "title": "Something broke",
        "description": "Details",
        "labels": "bug,urgent",
        "assignee_ids": [12, 34],
    }


@respx.mock
async def test_update_issue_puts_allowed_fields() -> None:
    route = respx.put(
        f"https://gitlab.com/api/v4/projects/{_ENCODED_PROJECT}/issues/7",
    ).mock(return_value=Response(200, json={"iid": 7}))
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "update_issue",
            "project_id": _PROJECT_PATH,
            "issue_iid": 7,
            "fields": {"state_event": "close", "title": "Renamed"},
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"state_event": "close", "title": "Renamed"}


@respx.mock
async def test_add_comment_posts_to_notes_endpoint() -> None:
    route = respx.post(
        f"https://gitlab.com/api/v4/projects/{_ENCODED_PROJECT}/issues/7/notes",
    ).mock(return_value=Response(201, json={"id": 99}))
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "add_comment",
            "project_id": _PROJECT_PATH,
            "issue_iid": 7,
            "body": "LGTM",
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"body": "LGTM"}


# --- list_issues / list_merge_requests ----------------------------------


@respx.mock
async def test_list_issues_surfaces_issues_convenience_key() -> None:
    route = respx.get(
        f"https://gitlab.com/api/v4/projects/{_ENCODED_PROJECT}/issues",
    ).mock(return_value=Response(200, json=[{"iid": 1}, {"iid": 2}]))
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "list_issues",
            "project_id": _PROJECT_PATH,
            "state": "opened",
            "labels": "bug,urgent",
            "per_page": 10,
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    out = await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [i["iid"] for i in result.json["issues"]] == [1, 2]
    query = dict(route.calls.last.request.url.params)
    assert query == {"state": "opened", "labels": "bug,urgent", "per_page": "10"}


@respx.mock
async def test_list_merge_requests_surfaces_merge_requests_key() -> None:
    route = respx.get(
        f"https://gitlab.com/api/v4/projects/{_ENCODED_PROJECT}/merge_requests",
    ).mock(return_value=Response(200, json=[{"iid": 100}]))
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "list_merge_requests",
            "project_id": _PROJECT_PATH,
            "state": "merged",
            "target_branch": "main",
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    out = await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [mr["iid"] for mr in result.json["merge_requests"]] == [100]
    query = dict(route.calls.last.request.url.params)
    assert query["state"] == "merged"
    assert query["target_branch"] == "main"


@respx.mock
async def test_list_issues_rejects_invalid_state() -> None:
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "list_issues",
            "project_id": _PROJECT_PATH,
            "state": "bogus",
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid issue state"):
        await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- error & credential paths -------------------------------------------


@respx.mock
async def test_api_error_surfaces_message_field() -> None:
    respx.get(
        f"https://gitlab.com/api/v4/projects/{_ENCODED_PROJECT}/issues/999",
    ).mock(return_value=Response(404, json={"message": "404 Not found"}))
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "get_issue",
            "project_id": _PROJECT_PATH,
            "issue_iid": 999,
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="404 Not found"):
        await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "get_issue",
            "project_id": _PROJECT_PATH,
            "issue_iid": 7,
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await GitLabNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_token_raises() -> None:
    node = Node(
        id="node_1",
        name="GitLab",
        type="weftlyflow.gitlab",
        parameters={
            "operation": "get_issue",
            "project_id": _PROJECT_PATH,
            "issue_iid": 7,
        },
        credentials={"gitlab_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'access_token'"):
        await GitLabNode().execute(
            _ctx_for(node, resolver=_resolver(access_token="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_create_requires_title() -> None:
    with pytest.raises(ValueError, match="'title' is required"):
        build_request("create_issue", {"project_id": "acme/widgets"})


def test_build_request_update_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown issue field"):
        build_request(
            "update_issue",
            {
                "project_id": "acme/widgets",
                "issue_iid": 1,
                "fields": {"title": "ok", "surprise": "no"},
            },
        )


def test_build_request_iid_must_be_positive_int() -> None:
    with pytest.raises(ValueError, match="'issue_iid'"):
        build_request(
            "get_issue", {"project_id": "acme/widgets", "issue_iid": 0},
        )


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("archive_all", {})
