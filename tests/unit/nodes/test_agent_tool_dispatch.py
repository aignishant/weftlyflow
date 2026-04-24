"""Unit tests for the ``agent_tool_dispatch`` node and its parsers."""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.agent_tool_dispatch import AgentToolDispatchNode
from weftlyflow.nodes.ai.agent_tool_dispatch.parsers import (
    SHAPE_ANTHROPIC,
    SHAPE_CUSTOM,
    SHAPE_OPENAI,
    parse,
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


# --- parsers ---------------------------------------------------------


def test_parse_openai_decodes_json_arguments_string() -> None:
    raw = [
        {
            "id": "call_1", "type": "function",
            "function": {
                "name": "lookup", "arguments": '{"q": "weather"}',
            },
        },
    ]
    calls = parse(SHAPE_OPENAI, raw)
    assert len(calls) == 1
    assert calls[0].tool_name == "lookup"
    assert calls[0].tool_args == {"q": "weather"}
    assert calls[0].tool_call_id == "call_1"


def test_parse_openai_retains_raw_arguments_on_decode_failure() -> None:
    raw = [
        {
            "id": "call_1", "type": "function",
            "function": {"name": "lookup", "arguments": "not json"},
        },
    ]
    calls = parse(SHAPE_OPENAI, raw)
    assert calls[0].tool_args == {"_raw": "not json"}


def test_parse_openai_skips_malformed_entries() -> None:
    raw = [
        "nope",
        {"id": "x"},  # no function
        {"function": {"name": "ok", "arguments": "{}"}, "id": "c"},
    ]
    calls = parse(SHAPE_OPENAI, raw)
    assert len(calls) == 1
    assert calls[0].tool_name == "ok"


def test_parse_anthropic_extracts_tool_use_blocks_only() -> None:
    raw = [
        {"type": "text", "text": "thinking"},
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "lookup",
            "input": {"q": "weather"},
        },
    ]
    calls = parse(SHAPE_ANTHROPIC, raw)
    assert len(calls) == 1
    assert calls[0].tool_name == "lookup"
    assert calls[0].tool_args == {"q": "weather"}


def test_parse_custom_accepts_pre_normalised_records() -> None:
    raw = [
        {
            "tool_name": "do_thing",
            "tool_args": {"a": 1},
            "tool_call_id": "c1",
        },
    ]
    calls = parse(SHAPE_CUSTOM, raw)
    assert calls[0].tool_name == "do_thing"
    assert calls[0].tool_args == {"a": 1}


def test_parse_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError, match="unsupported shape"):
        parse("bogus", [])


def test_parse_non_list_input_yields_empty() -> None:
    assert parse(SHAPE_OPENAI, None) == []
    assert parse(SHAPE_OPENAI, {}) == []


# --- node ------------------------------------------------------------


async def test_node_fans_openai_tool_calls_to_calls_port() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={},
    )
    response = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1", "type": "function",
                            "function": {
                                "name": "search",
                                "arguments": '{"q": "x"}',
                            },
                        },
                        {
                            "id": "c2", "type": "function",
                            "function": {
                                "name": "fetch",
                                "arguments": '{"url": "y"}',
                            },
                        },
                    ],
                },
            },
        ],
    }
    out = await AgentToolDispatchNode().execute(
        _ctx_for(node), [Item(json={"response": response})],
    )
    calls, content = out
    assert [c.json["tool_name"] for c in calls] == ["search", "fetch"]
    assert calls[0].json["call_total"] == 2
    assert content == []


async def test_node_emits_content_on_content_port_when_no_tools() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={},
    )
    response = {
        "choices": [
            {"message": {"content": "hello there", "tool_calls": []}},
        ],
    }
    out = await AgentToolDispatchNode().execute(
        _ctx_for(node), [Item(json={"response": response})],
    )
    calls, content = out
    assert calls == []
    assert content[0].json == {"content": "hello there"}


async def test_node_anthropic_splits_text_and_tool_use_blocks() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={"shape": "anthropic"},
    )
    response = {
        "content": [
            {"type": "text", "text": "let me check. "},
            {
                "type": "tool_use", "id": "t1",
                "name": "search", "input": {"q": "weftlyflow"},
            },
        ],
    }
    out = await AgentToolDispatchNode().execute(
        _ctx_for(node), [Item(json={"response": response})],
    )
    calls, content = out
    assert calls[0].json["tool_name"] == "search"
    assert content[0].json["content"] == "let me check. "


async def test_node_on_empty_skip_drops_items_without_calls_or_content() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={},
    )
    response = {"choices": [{"message": {"content": "", "tool_calls": []}}]}
    out = await AgentToolDispatchNode().execute(
        _ctx_for(node), [Item(json={"response": response})],
    )
    assert out == [[], []]


async def test_node_on_empty_emit_content_emits_empty_envelope() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={"on_empty": "emit_content"},
    )
    response = {"choices": [{"message": {"content": "", "tool_calls": []}}]}
    out = await AgentToolDispatchNode().execute(
        _ctx_for(node), [Item(json={"response": response})],
    )
    _, content = out
    assert content[0].json == {"content": ""}


async def test_node_on_empty_error_raises() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={"on_empty": "error"},
    )
    response = {"choices": [{"message": {"content": "", "tool_calls": []}}]}
    with pytest.raises(NodeExecutionError, match="no tool calls"):
        await AgentToolDispatchNode().execute(
            _ctx_for(node), [Item(json={"response": response})],
        )


async def test_node_custom_paths_override_defaults() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={
            "tool_calls_path": "data.calls",
            "content_path": "data.text",
        },
    )
    item_json = {
        "data": {
            "calls": [
                {
                    "id": "c1", "type": "function",
                    "function": {"name": "go", "arguments": "{}"},
                },
            ],
            "text": "ok",
        },
    }
    out = await AgentToolDispatchNode().execute(
        _ctx_for(node), [Item(json=item_json)],
    )
    calls, content = out
    assert calls[0].json["tool_name"] == "go"
    assert content[0].json["content"] == "ok"


async def test_node_rejects_unknown_shape() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={"shape": "claude-5"},
    )
    with pytest.raises(NodeExecutionError, match="shape"):
        await AgentToolDispatchNode().execute(_ctx_for(node), [Item(json={})])


async def test_node_rejects_unknown_on_empty() -> None:
    node = Node(
        id="d", name="d", type="weftlyflow.agent_tool_dispatch",
        parameters={"on_empty": "panic"},
    )
    with pytest.raises(NodeExecutionError, match="on_empty"):
        await AgentToolDispatchNode().execute(_ctx_for(node), [Item(json={})])
