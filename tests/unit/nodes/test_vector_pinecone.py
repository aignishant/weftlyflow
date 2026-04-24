"""Unit tests for :class:`VectorPineconeNode`.

No live Pinecone required - every request is intercepted with
``respx`` so each test asserts on URL, header, and body shape for a
single operation. Control-plane lookup (``GET /indexes/{name}``) is
exercised separately from the per-index data-plane operations since
Pinecone is the only retrieval backend whose host is dynamic.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PineconeApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.vector_pinecone import VectorPineconeNode

_CRED_ID: str = "cr_pinecone"
_PROJECT_ID: str = "pr_test"
_API_KEY: str = "pc-secret"
_INDEX: str = "weftlyflow-vectors"
_HOST: str = "https://my-index-proj.svc.us-east-1-aws.pinecone.io"
_CONTROL: str = "https://api.pinecone.io"


def _resolver(*, api_key: str = _API_KEY) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.pinecone_api": PineconeApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.pinecone_api",
                {"api_key": api_key},
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


def _node(**parameters: object) -> Node:
    return Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.vector_pinecone",
        parameters=dict(parameters),
        credentials={"pinecone_api": _CRED_ID},
    )


# --- credential plumbing --------------------------------------------


async def test_missing_credential_raises() -> None:
    node = _node(operation="clear", host=_HOST)
    ctx = ExecutionContext(
        workflow=build_workflow([node], [], project_id=_PROJECT_ID),
        execution_id="ex",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=None,
    )
    with pytest.raises(NodeExecutionError, match="pinecone_api credential"):
        await VectorPineconeNode().execute(ctx, [Item()])


@respx.mock
async def test_api_key_is_injected_as_api_key_header() -> None:
    route = respx.post(f"{_HOST}/vectors/delete").mock(
        return_value=httpx.Response(200, json={}),
    )
    node = _node(operation="clear", host=_HOST, namespace="ns")
    await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.headers["Api-Key"] == _API_KEY


# --- ensure_schema --------------------------------------------------


@respx.mock
async def test_ensure_schema_creates_index_when_absent() -> None:
    get_route = respx.get(f"{_CONTROL}/indexes/{_INDEX}").mock(
        return_value=httpx.Response(404),
    )
    post_route = respx.post(f"{_CONTROL}/indexes").mock(
        return_value=httpx.Response(201, json={"name": _INDEX}),
    )
    node = _node(operation="ensure_schema", dimensions=8, metric="cosine")
    out = await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    assert get_route.call_count == 1
    assert post_route.call_count == 1
    body = json.loads(post_route.calls.last.request.content)
    assert body == {
        "name": _INDEX,
        "dimension": 8,
        "metric": "cosine",
        "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}},
    }
    assert out[0][0].json["created"] is True


@respx.mock
async def test_ensure_schema_skips_creation_when_index_exists() -> None:
    get_route = respx.get(f"{_CONTROL}/indexes/{_INDEX}").mock(
        return_value=httpx.Response(200, json={"name": _INDEX, "host": _HOST}),
    )
    post_route = respx.post(f"{_CONTROL}/indexes")
    node = _node(operation="ensure_schema", dimensions=4)
    out = await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    assert get_route.call_count == 1
    assert post_route.call_count == 0
    assert out[0][0].json["created"] is False


@respx.mock
async def test_ensure_schema_maps_dot_to_dotproduct() -> None:
    respx.get(f"{_CONTROL}/indexes/{_INDEX}").mock(
        return_value=httpx.Response(404),
    )
    post_route = respx.post(f"{_CONTROL}/indexes").mock(
        return_value=httpx.Response(201, json={}),
    )
    node = _node(operation="ensure_schema", dimensions=2, metric="dot")
    await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(post_route.calls.last.request.content)
    assert body["metric"] == "dotproduct"


@respx.mock
async def test_ensure_schema_honours_custom_cloud_and_region() -> None:
    respx.get(f"{_CONTROL}/indexes/{_INDEX}").mock(
        return_value=httpx.Response(404),
    )
    post_route = respx.post(f"{_CONTROL}/indexes").mock(
        return_value=httpx.Response(201, json={}),
    )
    node = _node(
        operation="ensure_schema",
        dimensions=2,
        cloud="gcp",
        region="us-central1",
    )
    await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(post_route.calls.last.request.content)
    assert body["spec"]["serverless"] == {
        "cloud": "gcp", "region": "us-central1",
    }


# --- upsert ----------------------------------------------------------


@respx.mock
async def test_upsert_sends_vector_with_native_namespace() -> None:
    route = respx.post(f"{_HOST}/vectors/upsert").mock(
        return_value=httpx.Response(200, json={"upsertedCount": 1}),
    )
    node = _node(
        operation="upsert",
        host=_HOST,
        namespace="docs",
        id="doc-1",
        vector=[1.0, 0.0],
        metadata={"title": "hi"},
    )
    out = await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "vectors": [
            {
                "id": "doc-1",
                "values": [1.0, 0.0],
                "metadata": {"title": "hi"},
            },
        ],
        "namespace": "docs",
    }
    assert out[0][0].json["dimensions"] == 2


@respx.mock
async def test_upsert_coerces_integer_id_to_string() -> None:
    route = respx.post(f"{_HOST}/vectors/upsert").mock(
        return_value=httpx.Response(200, json={}),
    )
    node = _node(operation="upsert", host=_HOST, id=42, vector=[1.0])
    await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["vectors"][0]["id"] == "42"


async def test_upsert_rejects_boolean_id() -> None:
    node = _node(operation="upsert", host=_HOST, id=True, vector=[1.0])
    with pytest.raises(NodeExecutionError, match="must be a string"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


async def test_upsert_requires_id() -> None:
    node = _node(operation="upsert", host=_HOST, vector=[1.0])
    with pytest.raises(NodeExecutionError, match="'id' is required"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


async def test_upsert_rejects_non_numeric_vector() -> None:
    node = _node(
        operation="upsert", host=_HOST, id="x", vector=[1.0, "bad"],
    )
    with pytest.raises(NodeExecutionError, match="must be a number"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


# --- query -----------------------------------------------------------


@respx.mock
async def test_query_posts_to_query_with_namespace() -> None:
    route = respx.post(f"{_HOST}/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "matches": [
                    {"id": "a", "score": 0.9, "metadata": {"doc": "east"}},
                    {"id": "b", "score": 0.2, "metadata": {"doc": "north"}},
                ],
                "namespace": "docs",
            },
        ),
    )
    node = _node(
        operation="query",
        host=_HOST,
        namespace="docs",
        vector=[1.0, 0.0],
        top_k=2,
        metric="cosine",
    )
    out = await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "vector": [1.0, 0.0],
        "topK": 2,
        "namespace": "docs",
        "includeMetadata": True,
        "includeValues": False,
    }
    matches = out[0][0].json["matches"]
    assert matches[0] == {
        "id": "a", "metadata": {"doc": "east"}, "score": 0.9,
    }


@respx.mock
async def test_query_euclidean_negates_distance_for_normalized_score() -> None:
    respx.post(f"{_HOST}/query").mock(
        return_value=httpx.Response(
            200,
            json={"matches": [{"id": "a", "score": 2.5, "metadata": {}}]},
        ),
    )
    node = _node(
        operation="query", host=_HOST, vector=[0.0], top_k=1,
        metric="euclidean",
    )
    out = await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    assert out[0][0].json["matches"][0]["score"] == -2.5


async def test_query_rejects_unknown_metric() -> None:
    node = _node(
        operation="query", host=_HOST, vector=[1.0], metric="bogus",
    )
    with pytest.raises(NodeExecutionError, match="metric"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


async def test_query_rejects_non_positive_top_k() -> None:
    node = _node(
        operation="query", host=_HOST, vector=[1.0], top_k=0,
    )
    with pytest.raises(NodeExecutionError, match="top_k"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


# --- delete / clear --------------------------------------------------


@respx.mock
async def test_delete_sends_ids_with_namespace() -> None:
    route = respx.post(f"{_HOST}/vectors/delete").mock(
        return_value=httpx.Response(200, json={}),
    )
    node = _node(
        operation="delete", host=_HOST, namespace="docs", id="abc",
    )
    out = await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"ids": ["abc"], "namespace": "docs"}
    assert out[0][0].json["id"] == "abc"


@respx.mock
async def test_clear_sends_delete_all_flag() -> None:
    route = respx.post(f"{_HOST}/vectors/delete").mock(
        return_value=httpx.Response(200, json={}),
    )
    node = _node(operation="clear", host=_HOST, namespace="docs")
    out = await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"deleteAll": True, "namespace": "docs"}
    assert out[0][0].json["operation"] == "clear"


# --- host resolution -------------------------------------------------


@respx.mock
async def test_blank_host_resolves_via_control_plane() -> None:
    describe_route = respx.get(f"{_CONTROL}/indexes/{_INDEX}").mock(
        return_value=httpx.Response(
            200, json={"name": _INDEX, "host": _HOST.removeprefix("https://")},
        ),
    )
    delete_route = respx.post(f"{_HOST}/vectors/delete").mock(
        return_value=httpx.Response(200, json={}),
    )
    node = _node(operation="clear", namespace="ns")
    await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    assert describe_route.call_count == 1
    assert delete_route.call_count == 1


@respx.mock
async def test_control_plane_with_missing_host_raises() -> None:
    respx.get(f"{_CONTROL}/indexes/{_INDEX}").mock(
        return_value=httpx.Response(200, json={"name": _INDEX}),
    )
    node = _node(operation="clear", namespace="ns")
    with pytest.raises(NodeExecutionError, match="data-plane host"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_host_lookup_is_cached_across_items() -> None:
    describe_route = respx.get(f"{_CONTROL}/indexes/{_INDEX}").mock(
        return_value=httpx.Response(
            200, json={"name": _INDEX, "host": _HOST.removeprefix("https://")},
        ),
    )
    delete_route = respx.post(f"{_HOST}/vectors/delete").mock(
        return_value=httpx.Response(200, json={}),
    )
    node = _node(operation="clear", namespace="ns")
    # Drive two input items through the same execute call; host lookup
    # must only fire once even though the data-plane call fires twice.
    await VectorPineconeNode().execute(
        _ctx_for(node), [Item(), Item()],
    )
    assert describe_route.call_count == 1
    assert delete_route.call_count == 2


# --- error handling --------------------------------------------------


@respx.mock
async def test_api_error_is_wrapped_with_message() -> None:
    respx.post(f"{_HOST}/vectors/delete").mock(
        return_value=httpx.Response(403, json={"message": "forbidden"}),
    )
    node = _node(operation="clear", host=_HOST)
    with pytest.raises(NodeExecutionError, match="forbidden"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_network_error_is_wrapped() -> None:
    respx.post(f"{_HOST}/vectors/delete").mock(
        side_effect=httpx.ConnectError("boom"),
    )
    node = _node(operation="clear", host=_HOST)
    with pytest.raises(NodeExecutionError, match="network error"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


async def test_rejects_unknown_operation() -> None:
    node = _node(operation="nope")
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await VectorPineconeNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_bare_host_without_scheme_is_normalised() -> None:
    # Users who paste the hostname from describe_index without a
    # scheme must still reach the data plane.
    bare = _HOST.removeprefix("https://")
    route = respx.post(f"{_HOST}/vectors/delete").mock(
        return_value=httpx.Response(200, json={}),
    )
    node = _node(operation="clear", host=bare, namespace="ns")
    await VectorPineconeNode().execute(_ctx_for(node), [Item()])
    assert route.call_count == 1
