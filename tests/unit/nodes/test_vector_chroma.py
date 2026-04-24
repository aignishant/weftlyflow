"""Unit tests for :class:`VectorChromaNode`.

No live Chroma server required - every request is intercepted with
``respx`` so each test asserts on URL, header, and body shape for a
single operation. The collection-id lookup (``GET /collections/{name}``)
is exercised separately from the data-plane operations since Chroma
is the only retrieval backend whose per-op path changes after the
first call of an ``execute``.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ChromaCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.vector_chroma import VectorChromaNode

_CRED_ID: str = "cr_chroma"
_PROJECT_ID: str = "pr_test"
_BASE_URL: str = "http://chroma.local:8000"
_TOKEN: str = "ch-secret"
_COLLECTION: str = "weftlyflow_vectors"
_COLLECTION_ID: str = "11111111-2222-3333-4444-555555555555"
_TENANT: str = "default_tenant"
_DATABASE: str = "default_database"
_COLLECTIONS_PATH: str = (
    f"/api/v2/tenants/{_TENANT}/databases/{_DATABASE}/collections"
)


def _resolver(
    *,
    token: str = _TOKEN,
    base_url: str = _BASE_URL,
    tenant: str = _TENANT,
    database: str = _DATABASE,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.chroma": ChromaCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.chroma",
                {
                    "base_url": base_url,
                    "token": token,
                    "tenant": tenant,
                    "database": database,
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


def _node(**parameters: object) -> Node:
    return Node(
        id="node_1",
        name="Chroma",
        type="weftlyflow.vector_chroma",
        parameters=dict(parameters),
        credentials={"chroma": _CRED_ID},
    )


def _collection_body() -> dict[str, object]:
    return {"id": _COLLECTION_ID, "name": _COLLECTION}


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
    with pytest.raises(NodeExecutionError, match="chroma credential"):
        await VectorChromaNode().execute(ctx, [Item()])


@respx.mock
async def test_token_is_injected_as_bearer() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    delete_route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/delete",
    ).mock(return_value=httpx.Response(200, json={}))
    node = _node(operation="clear", namespace="ns")
    await VectorChromaNode().execute(_ctx_for(node), [Item()])
    assert (
        delete_route.calls.last.request.headers["Authorization"]
        == f"Bearer {_TOKEN}"
    )


@respx.mock
async def test_no_token_means_no_authorization_header() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    delete_route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/delete",
    ).mock(return_value=httpx.Response(200, json={}))
    node = _node(operation="clear", namespace="ns")
    await VectorChromaNode().execute(
        _ctx_for(node, resolver=_resolver(token="")), [Item()],
    )
    assert "Authorization" not in delete_route.calls.last.request.headers


# --- ensure_schema --------------------------------------------------


@respx.mock
async def test_ensure_schema_creates_collection_when_absent() -> None:
    get_route = respx.get(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}",
    ).mock(return_value=httpx.Response(404))
    post_route = respx.post(f"{_BASE_URL}{_COLLECTIONS_PATH}").mock(
        return_value=httpx.Response(201, json=_collection_body()),
    )
    node = _node(operation="ensure_schema", metric="cosine")
    out = await VectorChromaNode().execute(_ctx_for(node), [Item()])
    assert get_route.call_count == 1
    assert post_route.call_count == 1
    body = json.loads(post_route.calls.last.request.content)
    assert body == {
        "name": _COLLECTION,
        "configuration": {"hnsw": {"space": "cosine"}},
    }
    surfaced = out[0][0].json
    assert surfaced["created"] is True
    assert surfaced["collection_id"] == _COLLECTION_ID


@respx.mock
async def test_ensure_schema_skips_creation_when_collection_exists() -> None:
    get_route = respx.get(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}",
    ).mock(return_value=httpx.Response(200, json=_collection_body()))
    post_route = respx.post(f"{_BASE_URL}{_COLLECTIONS_PATH}")
    node = _node(operation="ensure_schema")
    out = await VectorChromaNode().execute(_ctx_for(node), [Item()])
    assert get_route.call_count == 1
    assert post_route.call_count == 0
    assert out[0][0].json["created"] is False


@respx.mock
async def test_ensure_schema_maps_dot_to_ip_space() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(404),
    )
    post_route = respx.post(f"{_BASE_URL}{_COLLECTIONS_PATH}").mock(
        return_value=httpx.Response(201, json=_collection_body()),
    )
    node = _node(operation="ensure_schema", metric="dot")
    await VectorChromaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(post_route.calls.last.request.content)
    assert body["configuration"]["hnsw"]["space"] == "ip"


@respx.mock
async def test_ensure_schema_maps_euclidean_to_l2_space() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(404),
    )
    post_route = respx.post(f"{_BASE_URL}{_COLLECTIONS_PATH}").mock(
        return_value=httpx.Response(201, json=_collection_body()),
    )
    node = _node(operation="ensure_schema", metric="euclidean")
    await VectorChromaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(post_route.calls.last.request.content)
    assert body["configuration"]["hnsw"]["space"] == "l2"


# --- collection id resolution ---------------------------------------


@respx.mock
async def test_upsert_resolves_collection_id_before_data_plane() -> None:
    get_route = respx.get(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}",
    ).mock(return_value=httpx.Response(200, json=_collection_body()))
    upsert_route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/upsert",
    ).mock(return_value=httpx.Response(200, json={}))
    node = _node(
        operation="upsert",
        namespace="docs",
        id="doc-1",
        vector=[1.0, 0.0],
        metadata={"title": "hi"},
    )
    await VectorChromaNode().execute(_ctx_for(node), [Item()])
    assert get_route.call_count == 1
    assert upsert_route.call_count == 1


@respx.mock
async def test_id_lookup_is_cached_across_items() -> None:
    get_route = respx.get(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}",
    ).mock(return_value=httpx.Response(200, json=_collection_body()))
    delete_route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/delete",
    ).mock(return_value=httpx.Response(200, json={}))
    node = _node(operation="clear", namespace="ns")
    await VectorChromaNode().execute(_ctx_for(node), [Item(), Item()])
    assert get_route.call_count == 1
    assert delete_route.call_count == 2


@respx.mock
async def test_missing_collection_raises_with_hint() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(404),
    )
    node = _node(operation="clear", namespace="ns")
    with pytest.raises(NodeExecutionError, match="ensure_schema"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


# --- upsert ----------------------------------------------------------


@respx.mock
async def test_upsert_sends_vector_with_namespace_marker_in_metadata() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/upsert",
    ).mock(return_value=httpx.Response(200, json={}))
    node = _node(
        operation="upsert",
        namespace="docs",
        id="doc-1",
        vector=[1.0, 0.0],
        metadata={"title": "hi"},
        document="hello world",
    )
    out = await VectorChromaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "ids": ["doc-1"],
        "embeddings": [[1.0, 0.0]],
        "metadatas": [{"title": "hi", "_weftlyflow_namespace": "docs"}],
        "documents": ["hello world"],
    }
    assert out[0][0].json["dimensions"] == 2


@respx.mock
async def test_upsert_omits_documents_when_no_document_given() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/upsert",
    ).mock(return_value=httpx.Response(200, json={}))
    node = _node(
        operation="upsert", id="x", vector=[1.0], metadata={},
    )
    await VectorChromaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert "documents" not in body


async def test_upsert_rejects_boolean_id() -> None:
    node = _node(operation="upsert", id=True, vector=[1.0])
    with pytest.raises(NodeExecutionError, match="must be a string"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


async def test_upsert_requires_id() -> None:
    node = _node(operation="upsert", vector=[1.0])
    with pytest.raises(NodeExecutionError, match="'id' is required"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


async def test_upsert_rejects_non_numeric_vector() -> None:
    node = _node(operation="upsert", id="x", vector=[1.0, "bad"])
    with pytest.raises(NodeExecutionError, match="must be a number"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


async def test_upsert_rejects_non_string_document() -> None:
    node = _node(
        operation="upsert", id="x", vector=[1.0], document=42,
    )
    with pytest.raises(NodeExecutionError, match="'document' must be a string"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


# --- query -----------------------------------------------------------


@respx.mock
async def test_query_posts_with_namespace_where_clause() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/query",
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "ids": [["a", "b"]],
                "distances": [[0.1, 0.4]],
                "metadatas": [[
                    {"doc": "east", "_weftlyflow_namespace": "docs"},
                    {"doc": "north", "_weftlyflow_namespace": "docs"},
                ]],
                "documents": [["east content", "north content"]],
            },
        ),
    )
    node = _node(
        operation="query", namespace="docs",
        vector=[1.0, 0.0], top_k=2, metric="cosine",
    )
    out = await VectorChromaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "query_embeddings": [[1.0, 0.0]],
        "n_results": 2,
        "where": {"_weftlyflow_namespace": "docs"},
        "include": ["metadatas", "documents", "distances"],
    }
    matches = out[0][0].json["matches"]
    # Distances are flipped to a "higher = better" score.
    assert matches[0] == {
        "id": "a",
        "metadata": {"doc": "east"},
        "document": "east content",
        "score": -0.1,
    }
    # Namespace marker must be stripped from surfaced metadata.
    assert "_weftlyflow_namespace" not in matches[0]["metadata"]


@respx.mock
async def test_query_handles_missing_documents_column() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/query",
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "ids": [["a"]],
                "distances": [[2.5]],
                "metadatas": [[{}]],
            },
        ),
    )
    node = _node(
        operation="query", vector=[0.0], top_k=1, metric="euclidean",
    )
    out = await VectorChromaNode().execute(_ctx_for(node), [Item()])
    match = out[0][0].json["matches"][0]
    assert match["document"] is None
    assert match["score"] == -2.5


async def test_query_rejects_unknown_metric() -> None:
    node = _node(operation="query", vector=[1.0], metric="bogus")
    with pytest.raises(NodeExecutionError, match="metric"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


async def test_query_rejects_non_positive_top_k() -> None:
    node = _node(operation="query", vector=[1.0], top_k=0)
    with pytest.raises(NodeExecutionError, match="top_k"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


# --- delete / clear --------------------------------------------------


@respx.mock
async def test_delete_scopes_by_id_and_namespace_where() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/delete",
    ).mock(return_value=httpx.Response(200, json={}))
    node = _node(operation="delete", namespace="docs", id="abc")
    out = await VectorChromaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "ids": ["abc"],
        "where": {"_weftlyflow_namespace": "docs"},
    }
    assert out[0][0].json["id"] == "abc"


@respx.mock
async def test_clear_filters_by_namespace_only() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    route = respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/delete",
    ).mock(return_value=httpx.Response(200, json={}))
    node = _node(operation="clear", namespace="docs")
    out = await VectorChromaNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"where": {"_weftlyflow_namespace": "docs"}}
    assert out[0][0].json["operation"] == "clear"


# --- error handling --------------------------------------------------


@respx.mock
async def test_api_error_is_wrapped_with_message() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        return_value=httpx.Response(200, json=_collection_body()),
    )
    respx.post(
        f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION_ID}/delete",
    ).mock(
        return_value=httpx.Response(403, json={"error": "forbidden"}),
    )
    node = _node(operation="clear")
    with pytest.raises(NodeExecutionError, match="forbidden"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_network_error_during_id_lookup_is_wrapped() -> None:
    respx.get(f"{_BASE_URL}{_COLLECTIONS_PATH}/{_COLLECTION}").mock(
        side_effect=httpx.ConnectError("boom"),
    )
    node = _node(operation="clear")
    with pytest.raises(NodeExecutionError, match="network error"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


async def test_rejects_unknown_operation() -> None:
    node = _node(operation="nope")
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])


async def test_blank_collection_rejected() -> None:
    node = _node(operation="clear", collection="")
    with pytest.raises(NodeExecutionError, match="'collection' is required"):
        await VectorChromaNode().execute(_ctx_for(node), [Item()])
