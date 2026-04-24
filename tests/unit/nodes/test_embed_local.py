"""Unit tests for the ``embed_local`` node and its hashing embedder."""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.embed_local import EmbedLocalNode
from weftlyflow.nodes.ai.embed_local.hasher import embed


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


# --- hasher ----------------------------------------------------------


def test_embed_returns_vector_of_requested_dimensions() -> None:
    out = embed("hello world", dimensions=32)
    assert len(out) == 32


def test_embed_empty_text_returns_zero_vector() -> None:
    out = embed("", dimensions=16)
    assert out == [0.0] * 16


def test_embed_is_deterministic_across_calls() -> None:
    a = embed("hello world", dimensions=64)
    b = embed("hello world", dimensions=64)
    assert a == b


def test_embed_is_case_insensitive() -> None:
    assert embed("Hello", dimensions=32) == embed("hello", dimensions=32)


def test_embed_normalised_vector_has_unit_norm() -> None:
    out = embed("hello world", dimensions=64)
    norm = math.sqrt(sum(x * x for x in out))
    assert norm == pytest.approx(1.0)


def test_embed_without_normalise_preserves_raw_counts() -> None:
    # Two tokens hash to two distinct buckets almost surely (64 dims), each
    # contributing ±1 -> raw norm should be sqrt(2), not 1.0.
    out = embed("hello world", dimensions=64, normalize=False)
    norm = math.sqrt(sum(x * x for x in out))
    assert norm == pytest.approx(math.sqrt(2.0))


def test_embed_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        embed("hi", dimensions=0)


def test_embed_similar_texts_have_higher_cosine_than_unrelated() -> None:
    a = embed("the quick brown fox", dimensions=256)
    b = embed("the quick brown dog", dimensions=256)
    c = embed("unrelated banana phone", dimensions=256)
    ab = sum(x * y for x, y in zip(a, b, strict=True))
    ac = sum(x * y for x, y in zip(a, c, strict=True))
    assert ab > ac


def test_embed_tokenises_on_non_alphanumeric() -> None:
    a = embed("hello,world!", dimensions=64)
    b = embed("hello world", dimensions=64)
    assert a == b


# --- node ------------------------------------------------------------


async def test_node_writes_embedding_to_default_output_field() -> None:
    node = Node(
        id="e", name="e", type="weftlyflow.embed_local",
        parameters={"text_field": "text", "dimensions": 32},
    )
    out = await EmbedLocalNode().execute(
        _ctx_for(node), [Item(json={"text": "hello world"})],
    )
    payload = out[0][0].json
    assert "embedding" in payload
    assert len(payload["embedding"]) == 32
    assert payload["embedding_dimensions"] == 32
    assert payload["embedding_model"] == "weftlyflow.embed_local"


async def test_node_preserves_source_fields() -> None:
    node = Node(
        id="e", name="e", type="weftlyflow.embed_local",
        parameters={"text_field": "text", "dimensions": 16},
    )
    out = await EmbedLocalNode().execute(
        _ctx_for(node),
        [Item(json={"text": "hi", "source": "doc.md"})],
    )
    assert out[0][0].json["source"] == "doc.md"


async def test_node_honours_custom_output_field() -> None:
    node = Node(
        id="e", name="e", type="weftlyflow.embed_local",
        parameters={
            "text_field": "text", "output_field": "vec", "dimensions": 16,
        },
    )
    out = await EmbedLocalNode().execute(
        _ctx_for(node), [Item(json={"text": "hi"})],
    )
    assert "vec" in out[0][0].json


async def test_node_defaults_to_chunk_field_for_splitter_fan_out() -> None:
    node = Node(
        id="e", name="e", type="weftlyflow.embed_local",
        parameters={"dimensions": 16},
    )
    # text_splitter's per_chunk output mode emits items with a "chunk" key.
    out = await EmbedLocalNode().execute(
        _ctx_for(node),
        [Item(json={"chunk": "hello", "chunk_index": 0})],
    )
    assert len(out[0][0].json["embedding"]) == 16


async def test_node_coerces_non_string_text_via_str() -> None:
    node = Node(
        id="e", name="e", type="weftlyflow.embed_local",
        parameters={"text_field": "n", "dimensions": 16},
    )
    out = await EmbedLocalNode().execute(
        _ctx_for(node), [Item(json={"n": 42})],
    )
    assert len(out[0][0].json["embedding"]) == 16


async def test_node_rejects_non_positive_dimensions() -> None:
    node = Node(
        id="e", name="e", type="weftlyflow.embed_local",
        parameters={"text_field": "text", "dimensions": 0},
    )
    with pytest.raises(NodeExecutionError, match="dimensions"):
        await EmbedLocalNode().execute(
            _ctx_for(node), [Item(json={"text": "hi"})],
        )


async def test_node_rejects_non_integer_dimensions() -> None:
    node = Node(
        id="e", name="e", type="weftlyflow.embed_local",
        parameters={"text_field": "text", "dimensions": "many"},
    )
    with pytest.raises(NodeExecutionError, match="integer"):
        await EmbedLocalNode().execute(
            _ctx_for(node), [Item(json={"text": "hi"})],
        )


async def test_node_normalize_false_emits_non_unit_vector() -> None:
    node = Node(
        id="e", name="e", type="weftlyflow.embed_local",
        parameters={
            "text_field": "text",
            "dimensions": 32,
            "normalize": False,
        },
    )
    out = await EmbedLocalNode().execute(
        _ctx_for(node),
        [Item(json={"text": "hello world and more"})],
    )
    vector = out[0][0].json["embedding"]
    norm = math.sqrt(sum(x * x for x in vector))
    # 4 tokens -> every coord in {-1, +1} before normalisation; norm = 2.0
    assert norm == pytest.approx(2.0)
