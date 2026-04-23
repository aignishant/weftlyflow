"""Unit tests for :class:`ContentfulNode` and ``ContentfulApiCredential``.

Exercises the distinctive split base URL (Management API
``api.contentful.com`` vs Delivery API ``cdn.contentful.com``), the
mandatory ``X-Contentful-Version`` header on optimistic-concurrency
writes, and the ``/spaces/{space}/environments/{env}/...`` path prefix.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ContentfulApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.contentful import ContentfulNode
from weftlyflow.nodes.integrations.contentful.operations import build_request

_CRED_ID: str = "cr_contentful"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "CFPAT-test-token"
_SPACE: str = "sp1"
_ENV: str = "master"
_CMA: str = "https://api.contentful.com"
_CDA: str = "https://cdn.contentful.com"


def _resolver(
    *,
    api_token: str = _TOKEN,
    space_id: str = _SPACE,
    environment: str = _ENV,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.contentful_api": ContentfulApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.contentful_api",
                {
                    "api_token": api_token,
                    "space_id": space_id,
                    "environment": environment,
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


# --- credential.inject ----------------------------------------------


async def test_credential_inject_sets_bearer_authorization() -> None:
    request = httpx.Request("GET", f"{_CMA}/spaces/{_SPACE}")
    out = await ContentfulApiCredential().inject(
        {"api_token": _TOKEN, "space_id": _SPACE, "environment": _ENV},
        request,
    )
    assert out.headers["Authorization"] == f"Bearer {_TOKEN}"


# --- list_entries (CDA) ---------------------------------------------


@respx.mock
async def test_list_entries_hits_cdn_host() -> None:
    route = respx.get(
        f"{_CDA}/spaces/{_SPACE}/environments/{_ENV}/entries",
    ).mock(return_value=Response(200, json={"items": []}))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={
            "operation": "list_entries",
            "content_type": "blogPost",
            "limit": 10,
            "order": "-sys.createdAt",
        },
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.url.host == "cdn.contentful.com"
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    params = request.url.params
    assert params["content_type"] == "blogPost"
    assert params["limit"] == "10"


@respx.mock
async def test_list_entries_merges_filter_map() -> None:
    route = respx.get(
        f"{_CDA}/spaces/{_SPACE}/environments/{_ENV}/entries",
    ).mock(return_value=Response(200, json={"items": []}))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={
            "operation": "list_entries",
            "filters": {"fields.slug": "home", "sys.id[in]": "a,b"},
        },
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["fields.slug"] == "home"
    assert params["sys.id[in]"] == "a,b"


# --- get_entry (CDA) / get_asset (CDA) ------------------------------


@respx.mock
async def test_get_entry_hits_cdn_host() -> None:
    respx.get(
        f"{_CDA}/spaces/{_SPACE}/environments/{_ENV}/entries/e1",
    ).mock(return_value=Response(200, json={"sys": {"id": "e1"}}))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={"operation": "get_entry", "entry_id": "e1"},
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_get_asset_hits_cdn_host() -> None:
    respx.get(
        f"{_CDA}/spaces/{_SPACE}/environments/{_ENV}/assets/a1",
    ).mock(return_value=Response(200, json={"sys": {"id": "a1"}}))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={"operation": "get_asset", "asset_id": "a1"},
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])


# --- create_entry (CMA) ----------------------------------------------


@respx.mock
async def test_create_entry_hits_cma_with_management_content_type() -> None:
    route = respx.post(
        f"{_CMA}/spaces/{_SPACE}/environments/{_ENV}/entries",
    ).mock(return_value=Response(201, json={"sys": {"id": "new"}}))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={
            "operation": "create_entry",
            "content_type": "blogPost",
            "fields": {"title": {"en-US": "Hello"}},
        },
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.url.host == "api.contentful.com"
    assert (
        request.headers["Content-Type"]
        == "application/vnd.contentful.management.v1+json"
    )
    assert request.url.params["content_type"] == "blogPost"
    body = json.loads(request.content)
    assert body == {"fields": {"title": {"en-US": "Hello"}}}
    assert "X-Contentful-Version" not in request.headers


def test_create_entry_requires_fields() -> None:
    with pytest.raises(ValueError, match="'fields' is required"):
        build_request(
            "create_entry",
            {"content_type": "x"},
            space_id=_SPACE,
            environment=_ENV,
        )


# --- update/publish/delete (versioned writes) -----------------------


@respx.mock
async def test_update_entry_sends_version_header() -> None:
    route = respx.put(
        f"{_CMA}/spaces/{_SPACE}/environments/{_ENV}/entries/e1",
    ).mock(return_value=Response(200, json={"sys": {"id": "e1", "version": 4}}))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={
            "operation": "update_entry",
            "entry_id": "e1",
            "version": 3,
            "fields": {"title": {"en-US": "Edit"}},
        },
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["X-Contentful-Version"] == "3"


@respx.mock
async def test_publish_entry_sends_empty_body_with_version_header() -> None:
    route = respx.put(
        f"{_CMA}/spaces/{_SPACE}/environments/{_ENV}/entries/e1/published",
    ).mock(return_value=Response(200, json={"sys": {"id": "e1"}}))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={
            "operation": "publish_entry",
            "entry_id": "e1",
            "version": 4,
        },
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["X-Contentful-Version"] == "4"
    assert request.content == b""


@respx.mock
async def test_delete_entry_requires_version_header() -> None:
    route = respx.delete(
        f"{_CMA}/spaces/{_SPACE}/environments/{_ENV}/entries/e1",
    ).mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={
            "operation": "delete_entry",
            "entry_id": "e1",
            "version": 2,
        },
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.headers["X-Contentful-Version"] == "2"


def test_update_entry_requires_version_and_fields() -> None:
    with pytest.raises(ValueError, match="'version' is required"):
        build_request(
            "update_entry",
            {"entry_id": "e1", "fields": {"a": {"en-US": 1}}},
            space_id=_SPACE,
            environment=_ENV,
        )
    with pytest.raises(ValueError, match="'fields' is required"):
        build_request(
            "update_entry",
            {"entry_id": "e1", "version": 1},
            space_id=_SPACE,
            environment=_ENV,
        )


def test_version_must_be_integer() -> None:
    with pytest.raises(ValueError, match="must be an integer"):
        build_request(
            "delete_entry",
            {"entry_id": "e1", "version": "abc"},
            space_id=_SPACE,
            environment=_ENV,
        )


# --- per-call overrides ---------------------------------------------


@respx.mock
async def test_environment_override_scopes_path() -> None:
    route = respx.get(
        f"{_CDA}/spaces/{_SPACE}/environments/staging/entries/e9",
    ).mock(return_value=Response(200, json={"sys": {"id": "e9"}}))
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={
            "operation": "get_entry",
            "entry_id": "e9",
            "environment": "staging",
        },
        credentials={"contentful_api": _CRED_ID},
    )
    await ContentfulNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- errors ----------------------------------------------------------


@respx.mock
async def test_error_envelope_is_parsed() -> None:
    respx.get(
        f"{_CDA}/spaces/{_SPACE}/environments/{_ENV}/entries/missing",
    ).mock(
        return_value=Response(
            404,
            json={
                "sys": {"type": "Error", "id": "NotFound"},
                "message": "The resource could not be found.",
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={"operation": "get_entry", "entry_id": "missing"},
        credentials={"contentful_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="could not be found"):
        await ContentfulNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Contentful",
        type="weftlyflow.contentful",
        parameters={"operation": "list_entries"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await ContentfulNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {}, space_id=_SPACE, environment=_ENV)


def test_space_required() -> None:
    with pytest.raises(ValueError, match="'space_id' is required"):
        build_request("list_entries", {}, space_id="", environment=_ENV)
