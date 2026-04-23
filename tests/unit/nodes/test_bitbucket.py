"""Unit tests for :class:`BitbucketNode` and ``BitbucketApiCredential``.

Exercises the distinctive workspace-scoped URL paths
(``/2.0/repositories/{workspace}/...``), Basic auth (NOT Bearer),
nested ``source.branch.name`` PR-creation envelope, and the credential
workspace-vs-per-call override.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BitbucketApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.bitbucket import BitbucketNode
from weftlyflow.nodes.integrations.bitbucket.operations import build_request

_CRED_ID: str = "cr_bitbucket"
_PROJECT_ID: str = "pr_test"
_USER: str = "alice"
_PASS: str = "app-password-xyz"
_WORKSPACE: str = "acme"
_BASE: str = "https://api.bitbucket.org"


def _resolver(
    *,
    username: str = _USER,
    app_password: str = _PASS,
    workspace: str = _WORKSPACE,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.bitbucket_api": BitbucketApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.bitbucket_api",
                {
                    "username": username,
                    "app_password": app_password,
                    "workspace": workspace,
                },
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


def _expected_basic() -> str:
    return "Basic " + base64.b64encode(f"{_USER}:{_PASS}".encode()).decode("ascii")


# --- credential.inject ----------------------------------------------


async def test_credential_inject_uses_basic_auth() -> None:
    request = httpx.Request("GET", f"{_BASE}/2.0/user")
    out = await BitbucketApiCredential().inject(
        {"username": _USER, "app_password": _PASS, "workspace": _WORKSPACE},
        request,
    )
    assert out.headers["Authorization"] == _expected_basic()


# --- list_repositories ----------------------------------------------


@respx.mock
async def test_list_repositories_scopes_path_with_workspace() -> None:
    route = respx.get(f"{_BASE}/2.0/repositories/{_WORKSPACE}").mock(
        return_value=Response(200, json={"values": []}),
    )
    node = Node(
        id="node_1",
        name="Bitbucket",
        type="weftlyflow.bitbucket",
        parameters={
            "operation": "list_repositories",
            "role": "owner",
            "pagelen": 10,
        },
        credentials={"bitbucket_api": _CRED_ID},
    )
    await BitbucketNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == _expected_basic()
    params = request.url.params
    assert params.get("role") == "owner"
    assert params.get("pagelen") == "10"


@respx.mock
async def test_list_repositories_workspace_per_call_override() -> None:
    route = respx.get(f"{_BASE}/2.0/repositories/other-ws").mock(
        return_value=Response(200, json={"values": []}),
    )
    node = Node(
        id="node_1",
        name="Bitbucket",
        type="weftlyflow.bitbucket",
        parameters={"operation": "list_repositories", "workspace": "other-ws"},
        credentials={"bitbucket_api": _CRED_ID},
    )
    await BitbucketNode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_workspace_required_when_credential_blank_and_no_override() -> None:
    with pytest.raises(ValueError, match="'workspace' is required"):
        build_request("list_repositories", {}, workspace="")


# --- get_repository -------------------------------------------------


@respx.mock
async def test_get_repository_hits_repo_path() -> None:
    respx.get(f"{_BASE}/2.0/repositories/{_WORKSPACE}/my-repo").mock(
        return_value=Response(200, json={"slug": "my-repo"}),
    )
    node = Node(
        id="node_1",
        name="Bitbucket",
        type="weftlyflow.bitbucket",
        parameters={"operation": "get_repository", "repo_slug": "my-repo"},
        credentials={"bitbucket_api": _CRED_ID},
    )
    await BitbucketNode().execute(_ctx_for(node), [Item()])


def test_get_repository_requires_slug() -> None:
    with pytest.raises(ValueError, match="'repo_slug' is required"):
        build_request("get_repository", {}, workspace=_WORKSPACE)


# --- pull requests --------------------------------------------------


@respx.mock
async def test_create_pull_request_wraps_branches_in_nested_envelope() -> None:
    route = respx.post(
        f"{_BASE}/2.0/repositories/{_WORKSPACE}/my-repo/pullrequests",
    ).mock(return_value=Response(201, json={"id": 42}))
    node = Node(
        id="node_1",
        name="Bitbucket",
        type="weftlyflow.bitbucket",
        parameters={
            "operation": "create_pull_request",
            "repo_slug": "my-repo",
            "title": "Add feature",
            "source_branch": "feature/x",
            "destination_branch": "main",
            "description": "What & why",
            "close_source_branch": True,
        },
        credentials={"bitbucket_api": _CRED_ID},
    )
    await BitbucketNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "title": "Add feature",
        "source": {"branch": {"name": "feature/x"}},
        "destination": {"branch": {"name": "main"}},
        "description": "What & why",
        "close_source_branch": True,
    }


def test_create_pr_requires_title_and_source() -> None:
    with pytest.raises(ValueError, match="'title' is required"):
        build_request(
            "create_pull_request",
            {"repo_slug": "r"},
            workspace=_WORKSPACE,
        )
    with pytest.raises(ValueError, match="'source_branch' is required"):
        build_request(
            "create_pull_request",
            {"repo_slug": "r", "title": "t"},
            workspace=_WORKSPACE,
        )


@respx.mock
async def test_get_pull_request_hits_pr_path() -> None:
    respx.get(
        f"{_BASE}/2.0/repositories/{_WORKSPACE}/my-repo/pullrequests/42",
    ).mock(return_value=Response(200, json={"id": 42}))
    node = Node(
        id="node_1",
        name="Bitbucket",
        type="weftlyflow.bitbucket",
        parameters={
            "operation": "get_pull_request",
            "repo_slug": "my-repo",
            "pull_request_id": "42",
        },
        credentials={"bitbucket_api": _CRED_ID},
    )
    await BitbucketNode().execute(_ctx_for(node), [Item()])


# --- issues ----------------------------------------------------------


@respx.mock
async def test_create_issue_wraps_content_raw() -> None:
    route = respx.post(
        f"{_BASE}/2.0/repositories/{_WORKSPACE}/my-repo/issues",
    ).mock(return_value=Response(201, json={"id": 1}))
    node = Node(
        id="node_1",
        name="Bitbucket",
        type="weftlyflow.bitbucket",
        parameters={
            "operation": "create_issue",
            "repo_slug": "my-repo",
            "title": "Bug",
            "content": "It crashes.",
            "kind": "bug",
            "priority": "major",
        },
        credentials={"bitbucket_api": _CRED_ID},
    )
    await BitbucketNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "title": "Bug",
        "content": {"raw": "It crashes."},
        "kind": "bug",
        "priority": "major",
    }


# --- errors ----------------------------------------------------------


@respx.mock
async def test_error_envelope_is_parsed() -> None:
    respx.get(f"{_BASE}/2.0/repositories/{_WORKSPACE}/missing").mock(
        return_value=Response(
            404,
            json={"type": "error", "error": {"message": "Repository not found"}},
        ),
    )
    node = Node(
        id="node_1",
        name="Bitbucket",
        type="weftlyflow.bitbucket",
        parameters={"operation": "get_repository", "repo_slug": "missing"},
        credentials={"bitbucket_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Repository not found"):
        await BitbucketNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Bitbucket",
        type="weftlyflow.bitbucket",
        parameters={"operation": "list_repositories"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await BitbucketNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {}, workspace=_WORKSPACE)
