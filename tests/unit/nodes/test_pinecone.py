"""Unit tests for :class:`PineconeNode` and ``PineconeApiCredential``.

Exercises the distinctive split between the control-plane host
(``https://api.pinecone.io``) and per-index data-plane hosts, the
flat ``Api-Key`` header, the ``topK`` camelCased body for query,
repeated-``ids`` query string for fetch, and the
``{"ids": [...] | "deleteAll": true}`` delete envelope.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PineconeApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.pinecone import PineconeNode
from weftlyflow.nodes.integrations.pinecone.operations import build_request

_CRED_ID: str = "cr_pinecone"
_PROJECT_ID: str = "pr_test"
_KEY: str = "pc-xyz"
_CONTROL: str = "https://api.pinecone.io"
_DATA_HOST: str = "my-idx-proj.svc.us-east-1-aws.pinecone.io"
_DATA_BASE: str = f"https://{_DATA_HOST}"


def _resolver(*, api_key: str = _KEY) -> InMemoryCredentialResolver:
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


# --- credential.inject ----------------------------------------------


async def test_credential_inject_sets_api_key_header() -> None:
    request = httpx.Request("GET", f"{_CONTROL}/indexes")
    out = await PineconeApiCredential().inject({"api_key": _KEY}, request)
    assert out.headers["Api-Key"] == _KEY
    assert "Authorization" not in out.headers


# --- control plane --------------------------------------------------


@respx.mock
async def test_list_indexes_hits_control_plane_host() -> None:
    route = respx.get(f"{_CONTROL}/indexes").mock(
        return_value=Response(200, json={"indexes": []}),
    )
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={"operation": "list_indexes"},
        credentials={"pinecone_api": _CRED_ID},
    )
    await PineconeNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.headers["Api-Key"] == _KEY


@respx.mock
async def test_describe_index_percent_encodes_name() -> None:
    route = respx.get(f"{_CONTROL}/indexes/my%20idx").mock(
        return_value=Response(200, json={"name": "my idx", "host": _DATA_HOST}),
    )
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={"operation": "describe_index", "index_name": "my idx"},
        credentials={"pinecone_api": _CRED_ID},
    )
    await PineconeNode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_describe_index_requires_name() -> None:
    with pytest.raises(ValueError, match="'index_name' is required"):
        build_request("describe_index", {})


# --- data plane: query ----------------------------------------------


@respx.mock
async def test_query_vectors_posts_camelcase_body_on_data_host() -> None:
    route = respx.post(f"{_DATA_BASE}/query").mock(
        return_value=Response(200, json={"matches": []}),
    )
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={
            "operation": "query_vectors",
            "host": _DATA_HOST,
            "top_k": 3,
            "vector": [0.1, 0.2, 0.3],
            "namespace": "ns1",
            "include_values": False,
            "include_metadata": True,
            "filter": {"genre": {"$eq": "rock"}},
        },
        credentials={"pinecone_api": _CRED_ID},
    )
    await PineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["topK"] == 3
    assert body["vector"] == [0.1, 0.2, 0.3]
    assert body["namespace"] == "ns1"
    assert body["includeValues"] is False
    assert body["includeMetadata"] is True
    assert body["filter"] == {"genre": {"$eq": "rock"}}


def test_query_vectors_requires_vector_or_id() -> None:
    with pytest.raises(ValueError, match="'vector' or 'id'"):
        build_request("query_vectors", {"top_k": 3})


def test_query_vectors_requires_positive_top_k() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        build_request("query_vectors", {"top_k": 0, "vector": [0.1]})


def test_query_vectors_requires_integer_top_k() -> None:
    with pytest.raises(ValueError, match="must be an integer"):
        build_request("query_vectors", {"top_k": "abc", "vector": [0.1]})


# --- data plane: upsert ---------------------------------------------


@respx.mock
async def test_upsert_vectors_sends_vectors_envelope() -> None:
    route = respx.post(f"{_DATA_BASE}/vectors/upsert").mock(
        return_value=Response(200, json={"upsertedCount": 1}),
    )
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={
            "operation": "upsert_vectors",
            "host": _DATA_HOST,
            "vectors": [{"id": "v1", "values": [0.1, 0.2]}],
            "namespace": "ns1",
        },
        credentials={"pinecone_api": _CRED_ID},
    )
    await PineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["vectors"][0]["id"] == "v1"
    assert body["namespace"] == "ns1"


def test_upsert_vectors_requires_non_empty_vectors() -> None:
    with pytest.raises(ValueError, match="'vectors' must be a non-empty list"):
        build_request("upsert_vectors", {})


# --- data plane: fetch ----------------------------------------------


@respx.mock
async def test_fetch_vectors_repeats_ids_query_param() -> None:
    route = respx.get(f"{_DATA_BASE}/vectors/fetch").mock(
        return_value=Response(200, json={"vectors": {}}),
    )
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={
            "operation": "fetch_vectors",
            "host": _DATA_HOST,
            "ids": ["v1", "v2"],
            "namespace": "ns1",
        },
        credentials={"pinecone_api": _CRED_ID},
    )
    await PineconeNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get_list("ids") == ["v1", "v2"]
    assert params["namespace"] == "ns1"


def test_fetch_vectors_requires_ids() -> None:
    with pytest.raises(ValueError, match="'ids' must be a non-empty list"):
        build_request("fetch_vectors", {})


# --- data plane: delete ---------------------------------------------


@respx.mock
async def test_delete_vectors_by_ids() -> None:
    route = respx.post(f"{_DATA_BASE}/vectors/delete").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={
            "operation": "delete_vectors",
            "host": _DATA_HOST,
            "ids": ["v1", "v2"],
        },
        credentials={"pinecone_api": _CRED_ID},
    )
    await PineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"ids": ["v1", "v2"]}


@respx.mock
async def test_delete_vectors_all_in_namespace() -> None:
    route = respx.post(f"{_DATA_BASE}/vectors/delete").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={
            "operation": "delete_vectors",
            "host": _DATA_HOST,
            "delete_all": True,
            "namespace": "ns1",
        },
        credentials={"pinecone_api": _CRED_ID},
    )
    await PineconeNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"deleteAll": True, "namespace": "ns1"}


def test_delete_vectors_requires_ids_or_delete_all() -> None:
    with pytest.raises(ValueError, match="'ids' or 'delete_all=true'"):
        build_request("delete_vectors", {})


# --- data-plane host requirement ------------------------------------


async def test_data_plane_operation_requires_host() -> None:
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={
            "operation": "query_vectors",
            "top_k": 3,
            "vector": [0.1],
        },
        credentials={"pinecone_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'host' parameter"):
        await PineconeNode().execute(_ctx_for(node), [Item()])


# --- errors ---------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.get(f"{_CONTROL}/indexes").mock(
        return_value=Response(401, json={"message": "invalid api key"}),
    )
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={"operation": "list_indexes"},
        credentials={"pinecone_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid api key"):
        await PineconeNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={"operation": "list_indexes"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await PineconeNode().execute(_ctx_for(node), [Item()])


async def test_empty_api_key_raises() -> None:
    resolver = _resolver(api_key="")
    node = Node(
        id="node_1",
        name="Pinecone",
        type="weftlyflow.pinecone",
        parameters={"operation": "list_indexes"},
        credentials={"pinecone_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_key'"):
        await PineconeNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
