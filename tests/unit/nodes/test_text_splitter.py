"""Unit tests for the ``text_splitter`` node and its splitter core.

Splitter tests cover separator priority, overlap, and the hard-slice
fallback for pathological inputs. Node tests cover both output modes,
field selection, error coercion, and empty-input handling.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.text_splitter import TextSplitterNode
from weftlyflow.nodes.ai.text_splitter.splitter import split_text


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


# --- splitter --------------------------------------------------------


def test_split_text_returns_single_chunk_when_text_fits() -> None:
    out = split_text("hello world", chunk_size=100, chunk_overlap=0)
    assert out == ["hello world"]


def test_split_text_returns_empty_list_on_empty_input() -> None:
    assert split_text("", chunk_size=10, chunk_overlap=0) == []


def test_split_text_splits_on_paragraph_boundary_first() -> None:
    text = "para1 line.\n\npara2 line.\n\npara3 line."
    out = split_text(text, chunk_size=20, chunk_overlap=0)
    # each "paraN line." fits; the "\n\n" sticks to the left piece.
    assert out[0].startswith("para1 line.")
    assert any("para2 line." in chunk for chunk in out)


def test_split_text_honours_overlap_between_chunks() -> None:
    text = "abcdefghijklmnop"  # 16 chars, no separators match
    out = split_text(
        text,
        chunk_size=8,
        chunk_overlap=3,
        separators=[""],  # force hard-slice
    )
    # greedy merge with tail overlap of 3 chars between chunks
    assert out == ["abcdefgh", "fghijklm", "klmnop"]
    assert out[0][-3:] == out[1][:3]
    assert out[1][-3:] == out[2][:3]


def test_split_text_rejects_bad_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        split_text("x", chunk_size=0, chunk_overlap=0)


def test_split_text_rejects_overlap_equal_to_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        split_text("x", chunk_size=10, chunk_overlap=10)


def test_split_text_rejects_negative_overlap() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        split_text("x", chunk_size=10, chunk_overlap=-1)


def test_split_text_custom_separators() -> None:
    text = "a|b|c|d|e"
    out = split_text(
        text, chunk_size=3, chunk_overlap=0, separators=["|", ""],
    )
    # pieces: "a|", "b|", "c|", "d|", "e" -> merged greedily at size 3
    assert "".join(out) == text


def test_split_text_falls_back_to_hard_slice_when_no_separator_fits() -> None:
    # long run with no spaces/newlines forces the "" sentinel path
    text = "x" * 25
    out = split_text(text, chunk_size=10, chunk_overlap=0)
    assert out == ["xxxxxxxxxx", "xxxxxxxxxx", "xxxxx"]


def test_split_text_sentence_splitter_uses_dot_space() -> None:
    text = "First sentence. Second sentence. Third sentence."
    out = split_text(text, chunk_size=20, chunk_overlap=0)
    assert all(len(chunk) <= 20 for chunk in out)
    assert "".join(out).replace("", "") == text.replace("", "")


# --- node ------------------------------------------------------------


async def test_node_fans_out_one_item_per_chunk_by_default() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={"chunk_size": 10, "chunk_overlap": 0},
    )
    item = Item(json={"text": "abcdefghij" * 3})  # 30 chars
    out = await TextSplitterNode().execute(_ctx_for(node), [item])
    payloads = [it.json for it in out[0]]
    assert len(payloads) == 3
    assert payloads[0]["chunk_index"] == 0
    assert payloads[0]["chunk_total"] == 3
    assert payloads[-1]["chunk_index"] == 2


async def test_node_list_mode_emits_single_item_with_chunks_list() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={
            "chunk_size": 10, "chunk_overlap": 0, "output_mode": "list",
        },
    )
    item = Item(json={"text": "abcdefghij" * 2, "meta": "keep"})
    out = await TextSplitterNode().execute(_ctx_for(node), [item])
    assert len(out[0]) == 1
    payload = out[0][0].json
    assert payload["meta"] == "keep"
    assert payload["chunk_total"] == 2
    assert len(payload["chunks"]) == 2


async def test_node_respects_custom_text_field() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={
            "text_field": "body", "chunk_size": 5, "chunk_overlap": 0,
        },
    )
    item = Item(json={"body": "hello world"})
    out = await TextSplitterNode().execute(_ctx_for(node), [item])
    assert next(it.json["chunk"] for it in out[0]).startswith("hello")


async def test_node_copies_source_fields_into_each_chunk_item() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={"chunk_size": 5, "chunk_overlap": 0},
    )
    item = Item(json={"text": "hello world", "source_url": "x"})
    out = await TextSplitterNode().execute(_ctx_for(node), [item])
    for sub in out[0]:
        assert sub.json["source_url"] == "x"


async def test_node_handles_empty_text_gracefully() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={"chunk_size": 10, "chunk_overlap": 0},
    )
    item = Item(json={"text": ""})
    out = await TextSplitterNode().execute(_ctx_for(node), [item])
    assert out[0] == []


async def test_node_rejects_bad_chunk_size_as_node_error() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={"chunk_size": "not-a-number"},
    )
    item = Item(json={"text": "hi"})
    with pytest.raises(NodeExecutionError, match="chunk_size"):
        await TextSplitterNode().execute(_ctx_for(node), [item])


async def test_node_rejects_non_list_separators() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={"separators": "not-a-list", "chunk_size": 10},
    )
    item = Item(json={"text": "hi"})
    with pytest.raises(NodeExecutionError, match="separators"):
        await TextSplitterNode().execute(_ctx_for(node), [item])


async def test_node_coerces_non_string_text_via_str() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={"chunk_size": 50, "chunk_overlap": 0},
    )
    item = Item(json={"text": 12345})
    out = await TextSplitterNode().execute(_ctx_for(node), [item])
    assert out[0][0].json["chunk"] == "12345"


async def test_node_unknown_output_mode_raises() -> None:
    node = Node(
        id="t", name="t", type="weftlyflow.text_splitter",
        parameters={
            "chunk_size": 10, "chunk_overlap": 0, "output_mode": "bogus",
        },
    )
    item = Item(json={"text": "hello"})
    with pytest.raises(NodeExecutionError, match="output_mode"):
        await TextSplitterNode().execute(_ctx_for(node), [item])
