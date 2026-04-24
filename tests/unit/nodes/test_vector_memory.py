"""Unit tests for the ``vector_memory`` node and its store core."""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.vector_memory import VectorMemoryNode
from weftlyflow.nodes.ai.vector_memory.store import (
    METRIC_COSINE,
    METRIC_DOT,
    METRIC_EUCLIDEAN,
    VECTOR_NAMESPACE,
    clear,
    delete,
    query,
    upsert,
)


def _ctx_for(
    node: Node,
    *,
    static_data: dict[str, Any] | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        static_data=static_data if static_data is not None else {},
    )


# --- store -----------------------------------------------------------


def test_store_upsert_inserts_new_record() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns", "a", [1.0, 0.0], {"doc": "alpha"})
    bucket = sd[VECTOR_NAMESPACE]["ns"]
    assert len(bucket) == 1
    assert bucket[0]["id"] == "a"


def test_store_upsert_replaces_existing_record_by_id() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns", "a", [1.0, 0.0], {"doc": "alpha"})
    upsert(sd, "ns", "a", [0.0, 1.0], {"doc": "alpha2"})
    bucket = sd[VECTOR_NAMESPACE]["ns"]
    assert len(bucket) == 1
    assert bucket[0]["vector"] == [0.0, 1.0]
    assert bucket[0]["payload"] == {"doc": "alpha2"}


def test_store_delete_removes_existing_record_and_returns_true() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns", "a", [1.0], {})
    assert delete(sd, "ns", "a") is True
    assert sd[VECTOR_NAMESPACE]["ns"] == []


def test_store_delete_returns_false_when_missing() -> None:
    assert delete({}, "ns", "missing") is False


def test_store_clear_drops_all_records_and_returns_count() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns", "a", [1.0], {})
    upsert(sd, "ns", "b", [2.0], {})
    assert clear(sd, "ns") == 2
    assert sd[VECTOR_NAMESPACE]["ns"] == []


def test_store_query_returns_top_k_sorted_by_cosine() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns", "a", [1.0, 0.0], {"label": "east"})
    upsert(sd, "ns", "b", [0.0, 1.0], {"label": "north"})
    upsert(sd, "ns", "c", [0.9, 0.1], {"label": "east-ish"})
    matches = query(
        sd, "ns", [1.0, 0.0], top_k=2, metric=METRIC_COSINE,
    )
    assert [m["id"] for m in matches] == ["a", "c"]
    assert matches[0]["score"] == pytest.approx(1.0)


def test_store_query_dot_metric_prefers_larger_magnitude() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns", "big", [10.0, 0.0], {})
    upsert(sd, "ns", "small", [1.0, 0.0], {})
    matches = query(sd, "ns", [1.0, 0.0], top_k=2, metric=METRIC_DOT)
    assert matches[0]["id"] == "big"


def test_store_query_euclidean_uses_negated_distance() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns", "close", [1.0, 0.0], {})
    upsert(sd, "ns", "far", [10.0, 0.0], {})
    matches = query(sd, "ns", [0.0, 0.0], top_k=2, metric=METRIC_EUCLIDEAN)
    # higher (less-negative) score wins -> closest first
    assert matches[0]["id"] == "close"
    assert matches[0]["score"] > matches[1]["score"]


def test_store_query_skips_records_with_mismatched_dimension() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns", "ok", [1.0, 0.0], {})
    upsert(sd, "ns", "wrong_dim", [1.0, 0.0, 0.0], {})
    matches = query(sd, "ns", [1.0, 0.0], top_k=5, metric=METRIC_COSINE)
    assert [m["id"] for m in matches] == ["ok"]


def test_store_query_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="unsupported metric"):
        query({}, "ns", [1.0], top_k=1, metric="bogus")


def test_store_query_rejects_non_positive_top_k() -> None:
    with pytest.raises(ValueError, match="top_k"):
        query({}, "ns", [1.0], top_k=0, metric=METRIC_COSINE)


def test_store_namespaces_are_isolated() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "ns1", "a", [1.0], {"tag": "one"})
    upsert(sd, "ns2", "a", [2.0], {"tag": "two"})
    assert query(
        sd, "ns1", [1.0], top_k=5, metric=METRIC_COSINE,
    )[0]["payload"]["tag"] == "one"
    assert query(
        sd, "ns2", [1.0], top_k=5, metric=METRIC_COSINE,
    )[0]["payload"]["tag"] == "two"


# --- node ------------------------------------------------------------


async def test_node_upsert_stores_record_in_static_data() -> None:
    sd: dict[str, Any] = {}
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={
            "operation": "upsert", "id": "doc1",
            "vector": [0.1, 0.2], "payload": {"source": "README"},
        },
    )
    out = await VectorMemoryNode().execute(_ctx_for(node, static_data=sd), [Item()])
    payload = out[0][0].json
    assert payload["operation"] == "upsert"
    assert payload["dimensions"] == 2
    assert sd[VECTOR_NAMESPACE]["default"][0]["id"] == "doc1"


async def test_node_query_returns_matches_sorted_by_score() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "default", "a", [1.0, 0.0], {"doc": "east"})
    upsert(sd, "default", "b", [0.0, 1.0], {"doc": "north"})
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={
            "operation": "query", "vector": [1.0, 0.0],
            "top_k": 2, "metric": "cosine",
        },
    )
    out = await VectorMemoryNode().execute(_ctx_for(node, static_data=sd), [Item()])
    payload = out[0][0].json
    assert payload["count"] == 2
    assert payload["matches"][0]["id"] == "a"
    assert payload["matches"][0]["payload"] == {"doc": "east"}


async def test_node_delete_reports_deleted_flag() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "default", "a", [1.0], {})
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={"operation": "delete", "id": "a"},
    )
    out = await VectorMemoryNode().execute(_ctx_for(node, static_data=sd), [Item()])
    assert out[0][0].json["deleted"] is True


async def test_node_clear_returns_count() -> None:
    sd: dict[str, Any] = {}
    upsert(sd, "default", "a", [1.0], {})
    upsert(sd, "default", "b", [2.0], {})
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={"operation": "clear"},
    )
    out = await VectorMemoryNode().execute(_ctx_for(node, static_data=sd), [Item()])
    assert out[0][0].json["cleared"] == 2


async def test_node_upsert_without_id_raises() -> None:
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={"operation": "upsert", "vector": [1.0]},
    )
    with pytest.raises(NodeExecutionError, match="'id' is required"):
        await VectorMemoryNode().execute(_ctx_for(node), [Item()])


async def test_node_rejects_non_numeric_vector_entries() -> None:
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={
            "operation": "upsert", "id": "a", "vector": [1.0, "bad"],
        },
    )
    with pytest.raises(NodeExecutionError, match="must be a number"):
        await VectorMemoryNode().execute(_ctx_for(node), [Item()])


async def test_node_rejects_empty_vector() -> None:
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={"operation": "upsert", "id": "a", "vector": []},
    )
    with pytest.raises(NodeExecutionError, match="non-empty"):
        await VectorMemoryNode().execute(_ctx_for(node), [Item()])


async def test_node_rejects_unknown_operation() -> None:
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={"operation": "nope"},
    )
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await VectorMemoryNode().execute(_ctx_for(node), [Item()])


async def test_node_query_rejects_non_positive_top_k() -> None:
    node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={"operation": "query", "vector": [1.0], "top_k": 0},
    )
    with pytest.raises(NodeExecutionError, match="top_k"):
        await VectorMemoryNode().execute(_ctx_for(node), [Item()])


async def test_node_namespace_isolates_records() -> None:
    sd: dict[str, Any] = {}
    upsert_node = Node(
        id="v", name="v", type="weftlyflow.vector_memory",
        parameters={
            "operation": "upsert", "namespace": "docs",
            "id": "x", "vector": [1.0], "payload": {"tag": "d"},
        },
    )
    await VectorMemoryNode().execute(_ctx_for(upsert_node, static_data=sd), [Item()])
    query_node = Node(
        id="q", name="q", type="weftlyflow.vector_memory",
        parameters={
            "operation": "query", "namespace": "other",
            "vector": [1.0], "top_k": 5,
        },
    )
    out = await VectorMemoryNode().execute(_ctx_for(query_node, static_data=sd), [Item()])
    assert out[0][0].json["matches"] == []
