"""Unit tests for the ``chat_respond`` node."""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.chat_respond import ChatRespondNode


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


async def test_node_reads_content_from_default_field() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond", parameters={},
    )
    out = await ChatRespondNode().execute(
        _ctx_for(node), [Item(json={"content": "hi there"})],
    )
    payload = out[0][0].json
    assert payload["content"] == "hi there"
    assert payload["role"] == "assistant"
    assert payload["response_type"] == "message"
    assert "ts" in payload


async def test_node_content_parameter_overrides_field() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={"content": "override"},
    )
    out = await ChatRespondNode().execute(
        _ctx_for(node), [Item(json={"content": "from-field"})],
    )
    assert out[0][0].json["content"] == "override"


async def test_node_custom_content_field() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={"content_field": "reply"},
    )
    out = await ChatRespondNode().execute(
        _ctx_for(node), [Item(json={"reply": "custom"})],
    )
    assert out[0][0].json["content"] == "custom"


async def test_node_copies_session_id_from_default_field() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond", parameters={},
    )
    out = await ChatRespondNode().execute(
        _ctx_for(node),
        [Item(json={"content": "hi", "session_id": "s-123"})],
    )
    assert out[0][0].json["session_id"] == "s-123"


async def test_node_empty_session_id_when_field_missing() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond", parameters={},
    )
    out = await ChatRespondNode().execute(
        _ctx_for(node), [Item(json={"content": "hi"})],
    )
    assert out[0][0].json["session_id"] == ""


async def test_node_custom_session_id_field() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={"session_id_field": "sid"},
    )
    out = await ChatRespondNode().execute(
        _ctx_for(node),
        [Item(json={"content": "hi", "sid": "alt"})],
    )
    assert out[0][0].json["session_id"] == "alt"


async def test_node_error_response_type_sets_envelope_flag() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={
            "content": "boom", "response_type": "error", "role": "system",
        },
    )
    out = await ChatRespondNode().execute(_ctx_for(node), [Item(json={})])
    payload = out[0][0].json
    assert payload["response_type"] == "error"
    assert payload["role"] == "system"


async def test_node_metadata_object_passed_through() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={"metadata": {"latency_ms": 120, "tokens": 45}},
    )
    out = await ChatRespondNode().execute(
        _ctx_for(node), [Item(json={"content": "ok"})],
    )
    assert out[0][0].json["metadata"] == {"latency_ms": 120, "tokens": 45}


async def test_node_non_dict_metadata_raises() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={"metadata": "not-a-dict"},
    )
    with pytest.raises(NodeExecutionError, match="metadata"):
        await ChatRespondNode().execute(_ctx_for(node), [Item(json={"content": "x"})])


async def test_node_rejects_unknown_role() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={"role": "wizard"},
    )
    with pytest.raises(NodeExecutionError, match="role"):
        await ChatRespondNode().execute(_ctx_for(node), [Item(json={"content": "x"})])


async def test_node_rejects_unknown_response_type() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={"response_type": "quantum"},
    )
    with pytest.raises(NodeExecutionError, match="response_type"):
        await ChatRespondNode().execute(_ctx_for(node), [Item(json={"content": "x"})])


async def test_node_emits_single_envelope_when_no_input_items() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond",
        parameters={"content": "hello"},
    )
    out = await ChatRespondNode().execute(_ctx_for(node), [])
    assert len(out[0]) == 1
    assert out[0][0].json["content"] == "hello"


async def test_node_coerces_non_string_content_field_via_str() -> None:
    node = Node(
        id="c", name="c", type="weftlyflow.chat_respond", parameters={},
    )
    out = await ChatRespondNode().execute(
        _ctx_for(node), [Item(json={"content": 42})],
    )
    assert out[0][0].json["content"] == "42"
