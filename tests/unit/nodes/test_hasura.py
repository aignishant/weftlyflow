"""Unit tests for :class:`HasuraNode` and ``HasuraApiCredential``.

Exercises the distinctive ``X-Hasura-Admin-Secret`` header + optional
role override, GraphQL ``{"query", "variables", "operationName"}`` body
shape, and the HTTP-200-with-``errors`` envelope that the node must
surface as a :class:`NodeExecutionError`.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import HasuraApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.hasura import HasuraNode
from weftlyflow.nodes.integrations.hasura.operations import build_request

_CRED_ID: str = "cr_hasura"
_PROJECT_ID: str = "pr_test"
_SECRET: str = "s3cret!"
_BASE: str = "https://gql.example.com"


def _resolver(
    *,
    admin_secret: str = _SECRET,
    base_url: str = _BASE,
    role: str = "",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.hasura_api": HasuraApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.hasura_api",
                {"base_url": base_url, "admin_secret": admin_secret, "role": role},
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


async def test_credential_inject_sets_admin_secret_header() -> None:
    request = httpx.Request("POST", f"{_BASE}/v1/graphql")
    out = await HasuraApiCredential().inject(
        {"admin_secret": _SECRET}, request,
    )
    assert out.headers["X-Hasura-Admin-Secret"] == _SECRET
    assert "X-Hasura-Role" not in out.headers


async def test_credential_inject_optional_role_header() -> None:
    request = httpx.Request("POST", f"{_BASE}/v1/graphql")
    out = await HasuraApiCredential().inject(
        {"admin_secret": _SECRET, "role": "user"}, request,
    )
    assert out.headers["X-Hasura-Role"] == "user"


# --- run_query ------------------------------------------------------


@respx.mock
async def test_run_query_posts_document_and_variables() -> None:
    route = respx.post(f"{_BASE}/v1/graphql").mock(
        return_value=Response(200, json={"data": {"users": []}}),
    )
    node = Node(
        id="node_1",
        name="Hasura",
        type="weftlyflow.hasura",
        parameters={
            "operation": "run_query",
            "query": "query Q($id: Int!) { users(where: {id: {_eq: $id}}) { id } }",
            "variables": {"id": 42},
            "operation_name": "Q",
        },
        credentials={"hasura_api": _CRED_ID},
    )
    await HasuraNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    body = json.loads(sent.content)
    assert body["query"].startswith("query Q")
    assert body["variables"] == {"id": 42}
    assert body["operationName"] == "Q"
    assert sent.headers["X-Hasura-Admin-Secret"] == _SECRET


def test_run_query_requires_query() -> None:
    with pytest.raises(ValueError, match="'query' is required"):
        build_request("run_query", {})


def test_run_query_rejects_non_dict_variables() -> None:
    with pytest.raises(ValueError, match="'variables' must be a JSON object"):
        build_request("run_query", {"query": "{ me { id } }", "variables": "nope"})


# --- run_mutation ---------------------------------------------------


@respx.mock
async def test_run_mutation_shares_document_builder() -> None:
    route = respx.post(f"{_BASE}/v1/graphql").mock(
        return_value=Response(200, json={"data": {"insert_users": {"affected_rows": 1}}}),
    )
    node = Node(
        id="node_1",
        name="Hasura",
        type="weftlyflow.hasura",
        parameters={
            "operation": "run_mutation",
            "query": "mutation { insert_users(objects: {email: \"a\"}) { affected_rows } }",
        },
        credentials={"hasura_api": _CRED_ID},
    )
    await HasuraNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert "insert_users" in body["query"]
    assert "variables" not in body


# --- introspect -----------------------------------------------------


@respx.mock
async def test_introspect_uses_canned_schema_query() -> None:
    route = respx.post(f"{_BASE}/v1/graphql").mock(
        return_value=Response(200, json={"data": {"__schema": {"queryType": {"name": "Q"}}}}),
    )
    node = Node(
        id="node_1",
        name="Hasura",
        type="weftlyflow.hasura",
        parameters={"operation": "introspect"},
        credentials={"hasura_api": _CRED_ID},
    )
    await HasuraNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert "__schema" in body["query"]
    assert body["operationName"] == "IntrospectionQuery"


# --- role override --------------------------------------------------


@respx.mock
async def test_per_call_role_overrides_credential_role() -> None:
    resolver = _resolver(role="admin")
    route = respx.post(f"{_BASE}/v1/graphql").mock(
        return_value=Response(200, json={"data": {}}),
    )
    node = Node(
        id="node_1",
        name="Hasura",
        type="weftlyflow.hasura",
        parameters={
            "operation": "run_query",
            "query": "{ me { id } }",
            "role": "editor",
        },
        credentials={"hasura_api": _CRED_ID},
    )
    await HasuraNode().execute(_ctx_for(node, resolver=resolver), [Item()])
    assert route.calls.last.request.headers["X-Hasura-Role"] == "editor"


# --- errors ---------------------------------------------------------


@respx.mock
async def test_graphql_errors_on_http_200_raise() -> None:
    respx.post(f"{_BASE}/v1/graphql").mock(
        return_value=Response(
            200,
            json={"errors": [{"message": "field 'bogus' not found"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="Hasura",
        type="weftlyflow.hasura",
        parameters={"operation": "run_query", "query": "{ bogus }"},
        credentials={"hasura_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="field 'bogus' not found"):
        await HasuraNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_http_error_is_wrapped() -> None:
    respx.post(f"{_BASE}/v1/graphql").mock(
        return_value=Response(401, json={"error": "unauthorized"}),
    )
    node = Node(
        id="node_1",
        name="Hasura",
        type="weftlyflow.hasura",
        parameters={"operation": "run_query", "query": "{ me { id } }"},
        credentials={"hasura_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unauthorized"):
        await HasuraNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Hasura",
        type="weftlyflow.hasura",
        parameters={"operation": "run_query", "query": "{ me { id } }"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await HasuraNode().execute(_ctx_for(node), [Item()])


async def test_empty_admin_secret_raises() -> None:
    resolver = _resolver(admin_secret="")
    node = Node(
        id="node_1",
        name="Hasura",
        type="weftlyflow.hasura",
        parameters={"operation": "run_query", "query": "{ me { id } }"},
        credentials={"hasura_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'admin_secret'"):
        await HasuraNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
