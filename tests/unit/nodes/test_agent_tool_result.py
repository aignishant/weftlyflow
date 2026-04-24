"""Unit tests for the ``agent_tool_result`` node and its encoders."""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.agent_tool_result import AgentToolResultNode
from weftlyflow.nodes.ai.agent_tool_result.encoders import (
    SHAPE_ANTHROPIC,
    SHAPE_OPENAI,
    ToolResult,
    coerce_content,
    encode_anthropic,
    encode_openai,
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


# --- encoders --------------------------------------------------------


def test_encode_openai_one_message_per_result() -> None:
    results = [
        ToolResult(tool_call_id="c1", content="a", is_error=False),
        ToolResult(tool_call_id="c2", content="b", is_error=True),
    ]
    msgs = encode_openai(results)
    assert msgs == [
        {"role": "tool", "tool_call_id": "c1", "content": "a"},
        {"role": "tool", "tool_call_id": "c2", "content": "b"},
    ]


def test_encode_anthropic_batches_into_single_user_message() -> None:
    results = [
        ToolResult(tool_call_id="t1", content="a", is_error=False),
        ToolResult(tool_call_id="t2", content="b", is_error=True),
    ]
    msgs = encode_anthropic(results, batch=True)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == [
        {"type": "tool_result", "tool_use_id": "t1", "content": "a"},
        {
            "type": "tool_result", "tool_use_id": "t2",
            "content": "b", "is_error": True,
        },
    ]


def test_encode_anthropic_non_batch_emits_one_message_each() -> None:
    results = [
        ToolResult(tool_call_id="t1", content="a", is_error=False),
        ToolResult(tool_call_id="t2", content="b", is_error=False),
    ]
    msgs = encode_anthropic(results, batch=False)
    assert len(msgs) == 2
    assert all(m["role"] == "user" for m in msgs)
    assert msgs[0]["content"][0]["tool_use_id"] == "t1"
    assert msgs[1]["content"][0]["tool_use_id"] == "t2"


def test_encode_anthropic_batch_empty_returns_empty() -> None:
    assert encode_anthropic([], batch=True) == []
    assert encode_anthropic([], batch=False) == []


def test_encode_anthropic_omits_is_error_when_false() -> None:
    msgs = encode_anthropic(
        [ToolResult(tool_call_id="t1", content="ok", is_error=False)],
        batch=True,
    )
    block = msgs[0]["content"][0]
    assert "is_error" not in block


def test_coerce_content_passes_through_strings() -> None:
    assert coerce_content("hello") == "hello"


def test_coerce_content_none_becomes_empty() -> None:
    assert coerce_content(None) == ""


def test_coerce_content_json_encodes_dicts() -> None:
    assert coerce_content({"a": 1}) == '{"a": 1}'


def test_coerce_content_json_encodes_lists_and_numbers() -> None:
    assert coerce_content([1, 2]) == "[1, 2]"
    assert coerce_content(42) == "42"
    assert coerce_content(True) == "true"


def test_coerce_content_falls_back_to_str_for_non_json_types() -> None:
    class Weird:
        def __str__(self) -> str:
            return "weird"

    assert coerce_content(Weird()) == "weird"


# --- node ------------------------------------------------------------


async def test_node_openai_default_wraps_each_item() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={},
    )
    items = [
        Item(json={"tool_call_id": "c1", "result": "ok"}),
        Item(json={"tool_call_id": "c2", "result": {"answer": 42}}),
    ]
    out = await AgentToolResultNode().execute(_ctx_for(node), items)
    msgs = [it.json["message"] for it in out[0]]
    assert msgs == [
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "tool", "tool_call_id": "c2", "content": '{"answer": 42}'},
    ]


async def test_node_anthropic_batches_by_default() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={"shape": "anthropic"},
    )
    items = [
        Item(json={"tool_call_id": "t1", "result": "a"}),
        Item(json={"tool_call_id": "t2", "result": "b", "is_error": True}),
    ]
    out = await AgentToolResultNode().execute(_ctx_for(node), items)
    assert len(out[0]) == 1
    msg = out[0][0].json["message"]
    assert msg["role"] == "user"
    assert len(msg["content"]) == 2
    assert msg["content"][1]["is_error"] is True


async def test_node_anthropic_non_batch_emits_one_message_per_item() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={"shape": "anthropic", "batch_anthropic": False},
    )
    items = [
        Item(json={"tool_call_id": "t1", "result": "a"}),
        Item(json={"tool_call_id": "t2", "result": "b"}),
    ]
    out = await AgentToolResultNode().execute(_ctx_for(node), items)
    assert len(out[0]) == 2


async def test_node_openai_ignores_is_error_flag() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={},
    )
    items = [Item(json={"tool_call_id": "c1", "result": "fail", "is_error": True})]
    out = await AgentToolResultNode().execute(_ctx_for(node), items)
    msg = out[0][0].json["message"]
    assert "is_error" not in msg
    assert msg == {"role": "tool", "tool_call_id": "c1", "content": "fail"}


async def test_node_custom_field_names_override_defaults() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={
            "tool_call_id_field": "call_id",
            "result_field": "payload",
        },
    )
    items = [Item(json={"call_id": "xyz", "payload": "done"})]
    out = await AgentToolResultNode().execute(_ctx_for(node), items)
    assert out[0][0].json["message"] == {
        "role": "tool", "tool_call_id": "xyz", "content": "done",
    }


async def test_node_missing_tool_call_id_raises() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={},
    )
    items = [Item(json={"result": "hello"})]
    with pytest.raises(NodeExecutionError, match="tool_call_id"):
        await AgentToolResultNode().execute(_ctx_for(node), items)


async def test_node_rejects_unknown_shape() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={"shape": "gemini"},
    )
    items = [Item(json={"tool_call_id": "c1", "result": "x"})]
    with pytest.raises(NodeExecutionError, match="shape"):
        await AgentToolResultNode().execute(_ctx_for(node), items)


async def test_node_empty_inputs_returns_empty_output() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={},
    )
    out = await AgentToolResultNode().execute(_ctx_for(node), [])
    assert out == [[]]


async def test_node_anthropic_coerces_truthy_string_is_error() -> None:
    node = Node(
        id="r", name="r", type="weftlyflow.agent_tool_result",
        parameters={"shape": "anthropic"},
    )
    items = [Item(json={"tool_call_id": "t1", "result": "boom", "is_error": "true"})]
    out = await AgentToolResultNode().execute(_ctx_for(node), items)
    block = out[0][0].json["message"]["content"][0]
    assert block["is_error"] is True


def test_shape_constants_exported() -> None:
    assert SHAPE_OPENAI == "openai"
    assert SHAPE_ANTHROPIC == "anthropic"
