"""Unit tests for :class:`VectorQdrantNode`.

No live Qdrant required — requests are intercepted with ``respx`` so
we can assert on URL, headers, and body shape for each operation.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import QdrantApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.vector_qdrant import VectorQdrantNode

_CRED_ID: str = "cr_qdrant"
_PROJECT_ID: str = "pr_test"
_BASE_URL: str = "http://qdrant.local:6333"
_API_KEY: str = "qd-secret"
_COLLECTION: str = "weftlyflow_vectors"


def _resolver(
    *, api_key: str = _API_KEY, base_url: str = _BASE_URL,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.qdrant_api": QdrantApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.qdrant_api",
                {"base_url": base_url, "api_key": api_key},
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
        name="Qdrant",
        type="weftlyflow.vector_qdrant",
        parameters=dict(parameters),
        credentials={"qdrant_api": _CRED_ID},
    )


# --- credential plumbing --------------------------------------------


async def test_missing_credential_raises() -> None:
    node = _node(operation="clear")
    ctx = ExecutionContext(
        workflow=build_workflow([node], [], project_id=_PROJECT_ID),
        execution_id="ex",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=None,
    )
    with pytest.raises(NodeExecutionError, match="qdrant_api credential"):
        await VectorQdrantNode().execute(ctx, [Item()])


@respx.mock
async def test_api_key_is_injected_as_api_key_header() -> None:
    route = respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/delete",
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
    node = _node(operation="clear", namespace="ns")
    await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.headers["api-key"] == _API_KEY


@respx.mock
async def test_no_api_key_means_no_api_key_header() -> None:
    route = respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/delete",
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
    node = _node(operation="clear", namespace="ns")
    await VectorQdrantNode().execute(
        _ctx_for(node, resolver=_resolver(api_key="")), [Item()],
    )
    assert "api-key" not in route.calls.last.request.headers


# --- ensure_schema --------------------------------------------------


@respx.mock
async def test_ensure_schema_creates_collection_when_absent() -> None:
    get_route = respx.get(
        f"{_BASE_URL}/collections/{_COLLECTION}",
    ).mock(return_value=httpx.Response(404))
    put_route = respx.put(
        f"{_BASE_URL}/collections/{_COLLECTION}",
    ).mock(return_value=httpx.Response(200, json={"result": True}))
    node = _node(
        operation="ensure_schema", dimensions=8, metric="cosine",
    )
    out = await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    assert get_route.call_count == 1
    assert put_route.call_count == 1
    body = json.loads(put_route.calls.last.request.content)
    assert body == {"vectors": {"size": 8, "distance": "Cosine"}}
    assert out[0][0].json["created"] is True


@respx.mock
async def test_ensure_schema_skips_creation_when_collection_exists() -> None:
    get_route = respx.get(
        f"{_BASE_URL}/collections/{_COLLECTION}",
    ).mock(return_value=httpx.Response(200, json={"result": {}}))
    put_route = respx.put(f"{_BASE_URL}/collections/{_COLLECTION}")
    node = _node(operation="ensure_schema", dimensions=4)
    out = await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    assert get_route.call_count == 1
    assert put_route.call_count == 0
    assert out[0][0].json["created"] is False


@respx.mock
async def test_ensure_schema_maps_euclidean_metric_to_euclid() -> None:
    respx.get(
        f"{_BASE_URL}/collections/{_COLLECTION}",
    ).mock(return_value=httpx.Response(404))
    put_route = respx.put(
        f"{_BASE_URL}/collections/{_COLLECTION}",
    ).mock(return_value=httpx.Response(200, json={"result": True}))
    node = _node(
        operation="ensure_schema", dimensions=2, metric="euclidean",
    )
    await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    assert (
        json.loads(put_route.calls.last.request.content)["vectors"]["distance"]
        == "Euclid"
    )


# --- upsert ----------------------------------------------------------


@respx.mock
async def test_upsert_sends_point_with_namespace_embedded_in_payload() -> None:
    route = respx.put(
        f"{_BASE_URL}/collections/{_COLLECTION}/points",
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
    node = _node(
        operation="upsert",
        namespace="docs",
        id="550e8400-e29b-41d4-a716-446655440000",
        vector=[1.0, 0.0],
        payload={"title": "hi"},
    )
    out = await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert route.calls.last.request.url.query == b"wait=true"
    point = body["points"][0]
    assert point["id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert point["vector"] == [1.0, 0.0]
    assert point["payload"] == {
        "title": "hi", "_weftlyflow_namespace": "docs",
    }
    assert out[0][0].json["dimensions"] == 2


@respx.mock
async def test_upsert_accepts_integer_id() -> None:
    route = respx.put(
        f"{_BASE_URL}/collections/{_COLLECTION}/points",
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
    node = _node(
        operation="upsert", id=42, vector=[1.0], payload={},
    )
    await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["points"][0]["id"] == 42


async def test_upsert_rejects_negative_integer_id() -> None:
    node = _node(operation="upsert", id=-1, vector=[1.0])
    with pytest.raises(NodeExecutionError, match="non-negative"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


async def test_upsert_rejects_boolean_id() -> None:
    node = _node(operation="upsert", id=True, vector=[1.0])
    with pytest.raises(NodeExecutionError, match="string or integer"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


async def test_upsert_requires_id() -> None:
    node = _node(operation="upsert", vector=[1.0])
    with pytest.raises(NodeExecutionError, match="'id' is required"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


async def test_upsert_rejects_non_numeric_vector() -> None:
    node = _node(operation="upsert", id="x", vector=[1.0, "bad"])
    with pytest.raises(NodeExecutionError, match="must be a number"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


# --- query -----------------------------------------------------------


@respx.mock
async def test_query_posts_to_search_with_namespace_filter() -> None:
    route = respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/search",
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [
                    {
                        "id": "a",
                        "score": 0.9,
                        "payload": {
                            "doc": "east",
                            "_weftlyflow_namespace": "docs",
                        },
                    },
                    {
                        "id": "b",
                        "score": 0.2,
                        "payload": {
                            "doc": "north",
                            "_weftlyflow_namespace": "docs",
                        },
                    },
                ],
            },
        ),
    )
    node = _node(
        operation="query", namespace="docs",
        vector=[1.0, 0.0], top_k=2, metric="cosine",
    )
    out = await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["vector"] == [1.0, 0.0]
    assert body["limit"] == 2
    assert body["with_payload"] is True
    assert body["filter"] == {
        "must": [
            {"key": "_weftlyflow_namespace", "match": {"value": "docs"}},
        ],
    }
    matches = out[0][0].json["matches"]
    assert matches[0] == {"id": "a", "payload": {"doc": "east"}, "score": 0.9}
    # Namespace marker must be stripped from surfaced payload.
    assert "_weftlyflow_namespace" not in matches[0]["payload"]


@respx.mock
async def test_query_euclidean_negates_distance_for_normalized_score() -> None:
    respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/search",
    ).mock(
        return_value=httpx.Response(
            200,
            json={"result": [{"id": "a", "score": 2.5, "payload": {}}]},
        ),
    )
    node = _node(
        operation="query", vector=[0.0], top_k=1, metric="euclidean",
    )
    out = await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    assert out[0][0].json["matches"][0]["score"] == -2.5


async def test_query_rejects_unknown_metric() -> None:
    node = _node(operation="query", vector=[1.0], metric="bogus")
    with pytest.raises(NodeExecutionError, match="metric"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


async def test_query_rejects_non_positive_top_k() -> None:
    node = _node(operation="query", vector=[1.0], top_k=0)
    with pytest.raises(NodeExecutionError, match="top_k"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


# --- delete / clear --------------------------------------------------


@respx.mock
async def test_delete_filters_by_id_and_namespace() -> None:
    route = respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/delete",
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
    node = _node(operation="delete", namespace="docs", id="abc")
    out = await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["filter"]["must"] == [
        {"has_id": ["abc"]},
        {"key": "_weftlyflow_namespace", "match": {"value": "docs"}},
    ]
    assert out[0][0].json["id"] == "abc"


@respx.mock
async def test_clear_filters_by_namespace_only() -> None:
    route = respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/delete",
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
    node = _node(operation="clear", namespace="docs")
    out = await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "filter": {
            "must": [
                {"key": "_weftlyflow_namespace", "match": {"value": "docs"}},
            ],
        },
    }
    assert out[0][0].json["operation"] == "clear"


# --- error handling --------------------------------------------------


@respx.mock
async def test_api_error_is_wrapped_with_message() -> None:
    respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/delete",
    ).mock(
        return_value=httpx.Response(
            403, json={"status": {"error": "forbidden"}},
        ),
    )
    node = _node(operation="clear")
    with pytest.raises(NodeExecutionError, match="forbidden"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_network_error_is_wrapped() -> None:
    respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/delete",
    ).mock(side_effect=httpx.ConnectError("boom"))
    node = _node(operation="clear")
    with pytest.raises(NodeExecutionError, match="network error"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


async def test_rejects_unknown_operation() -> None:
    node = _node(operation="nope")
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await VectorQdrantNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_blank_collection_falls_back_to_default() -> None:
    # Empty string takes the documented default instead of erroring —
    # matches vector_memory / vector_pgvector's lenient fallback.
    route = respx.post(
        f"{_BASE_URL}/collections/{_COLLECTION}/points/delete",
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
    node = _node(operation="clear", collection="", namespace="ns")
    await VectorQdrantNode().execute(_ctx_for(node), [Item()])
    assert route.call_count == 1
