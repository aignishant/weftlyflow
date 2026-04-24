"""Unit tests for the session-keyed memory nodes.

Covers the shared :mod:`weftlyflow.nodes.ai.memory_store` helpers and
the three memory nodes — :class:`MemoryBufferNode` (unbounded history),
:class:`MemoryWindowNode` (sliding window), and
:class:`MemorySummaryNode` (rolling summary + bounded tail). Also
exercises the shared backing-store semantics: buffer and window nodes
keyed by the same ``session_id`` see one conversation, while summary
lives in its own namespace.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.memory_buffer import MemoryBufferNode
from weftlyflow.nodes.ai.memory_store import (
    MEMORY_NAMESPACE,
    MEMORY_SUMMARY_NAMESPACE,
    append_history,
    append_summary_messages,
    clear_history,
    clear_summary,
    load_history,
    load_summary,
    replace_summary,
)
from weftlyflow.nodes.ai.memory_summary import MemorySummaryNode
from weftlyflow.nodes.ai.memory_window import MemoryWindowNode

_SESSION: str = "sess-42"


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


# --- store helpers ---------------------------------------------------


def test_load_history_empty_returns_empty_list() -> None:
    assert load_history({}, _SESSION) == []


def test_append_then_load_roundtrip() -> None:
    store: dict[str, Any] = {}
    append_history(store, _SESSION, [{"role": "user", "content": "hi"}])
    assert load_history(store, _SESSION) == [{"role": "user", "content": "hi"}]


def test_append_returns_copy_not_live_reference() -> None:
    store: dict[str, Any] = {}
    snapshot = append_history(store, _SESSION, [{"role": "user", "content": "hi"}])
    snapshot.append({"role": "assistant", "content": "mutated"})
    assert load_history(store, _SESSION) == [{"role": "user", "content": "hi"}]


def test_append_with_max_len_trims_to_tail() -> None:
    store: dict[str, Any] = {}
    for i in range(5):
        append_history(store, _SESSION, [{"role": "user", "content": str(i)}], max_len=3)
    result = load_history(store, _SESSION)
    assert [msg["content"] for msg in result] == ["2", "3", "4"]


def test_append_rejects_non_positive_max_len() -> None:
    with pytest.raises(ValueError, match="max_len must be >= 1"):
        append_history({}, _SESSION, [], max_len=0)


def test_clear_history_drops_session() -> None:
    store: dict[str, Any] = {}
    append_history(store, _SESSION, [{"role": "user", "content": "hi"}])
    clear_history(store, _SESSION)
    assert load_history(store, _SESSION) == []


def test_sessions_are_isolated() -> None:
    store: dict[str, Any] = {}
    append_history(store, "a", [{"role": "user", "content": "A"}])
    append_history(store, "b", [{"role": "user", "content": "B"}])
    assert load_history(store, "a") == [{"role": "user", "content": "A"}]
    assert load_history(store, "b") == [{"role": "user", "content": "B"}]


def test_namespace_constant_used_in_static_data() -> None:
    store: dict[str, Any] = {}
    append_history(store, _SESSION, [{"role": "user", "content": "hi"}])
    assert MEMORY_NAMESPACE in store


# --- MemoryBufferNode ------------------------------------------------


async def test_buffer_load_on_empty_returns_empty_messages() -> None:
    node = Node(
        id="n_mem", name="mem", type="weftlyflow.memory_buffer",
        parameters={"session_id": _SESSION, "operation": "load"},
    )
    ctx = _ctx_for(node)
    out = await MemoryBufferNode().execute(ctx, [Item()])
    assert out[0][0].json == {
        "session_id": _SESSION, "operation": "load", "messages": [], "count": 0,
    }


async def test_buffer_append_returns_cumulative_history() -> None:
    state: dict[str, Any] = {}
    node = Node(
        id="n_mem", name="mem", type="weftlyflow.memory_buffer",
        parameters={
            "session_id": _SESSION,
            "operation": "append",
            "new_messages": [{"role": "user", "content": "hi"}],
        },
    )
    ctx = _ctx_for(node, static_data=state)
    await MemoryBufferNode().execute(ctx, [Item()])

    node.parameters["new_messages"] = [{"role": "assistant", "content": "hello"}]
    out = await MemoryBufferNode().execute(ctx, [Item()])
    payload = out[0][0].json
    assert payload["count"] == 2
    assert [msg["content"] for msg in payload["messages"]] == ["hi", "hello"]


async def test_buffer_clear_drops_session() -> None:
    state: dict[str, Any] = {}
    append_history(state, _SESSION, [{"role": "user", "content": "hi"}])
    node = Node(
        id="n_mem", name="mem", type="weftlyflow.memory_buffer",
        parameters={"session_id": _SESSION, "operation": "clear"},
    )
    out = await MemoryBufferNode().execute(_ctx_for(node, static_data=state), [Item()])
    assert out[0][0].json["messages"] == []
    assert load_history(state, _SESSION) == []


async def test_buffer_requires_session_id() -> None:
    node = Node(
        id="n_mem", name="mem", type="weftlyflow.memory_buffer",
        parameters={"session_id": "", "operation": "load"},
    )
    with pytest.raises(NodeExecutionError, match="'session_id' is required"):
        await MemoryBufferNode().execute(_ctx_for(node), [Item()])


async def test_buffer_rejects_unknown_operation() -> None:
    node = Node(
        id="n_mem", name="mem", type="weftlyflow.memory_buffer",
        parameters={"session_id": _SESSION, "operation": "nuke"},
    )
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await MemoryBufferNode().execute(_ctx_for(node), [Item()])


async def test_buffer_rejects_non_list_new_messages() -> None:
    node = Node(
        id="n_mem", name="mem", type="weftlyflow.memory_buffer",
        parameters={
            "session_id": _SESSION,
            "operation": "append",
            "new_messages": "not-a-list",
        },
    )
    with pytest.raises(NodeExecutionError, match="must be a JSON array"):
        await MemoryBufferNode().execute(_ctx_for(node), [Item()])


# --- MemoryWindowNode ------------------------------------------------


async def test_window_append_trims_to_window_size() -> None:
    state: dict[str, Any] = {}
    for i in range(5):
        node = Node(
            id="n_win", name="win", type="weftlyflow.memory_window",
            parameters={
                "session_id": _SESSION,
                "operation": "append",
                "window_size": 3,
                "new_messages": [{"role": "user", "content": str(i)}],
            },
        )
        await MemoryWindowNode().execute(_ctx_for(node, static_data=state), [Item()])

    result = load_history(state, _SESSION)
    assert [msg["content"] for msg in result] == ["2", "3", "4"]


async def test_window_load_truncates_even_when_store_is_larger() -> None:
    state: dict[str, Any] = {}
    for i in range(5):
        append_history(state, _SESSION, [{"role": "user", "content": str(i)}])
    node = Node(
        id="n_win", name="win", type="weftlyflow.memory_window",
        parameters={"session_id": _SESSION, "operation": "load", "window_size": 2},
    )
    out = await MemoryWindowNode().execute(_ctx_for(node, static_data=state), [Item()])
    payload = out[0][0].json
    assert payload["count"] == 2
    assert [msg["content"] for msg in payload["messages"]] == ["3", "4"]


async def test_window_rejects_non_positive_window_size() -> None:
    node = Node(
        id="n_win", name="win", type="weftlyflow.memory_window",
        parameters={"session_id": _SESSION, "operation": "load", "window_size": 0},
    )
    with pytest.raises(NodeExecutionError, match="'window_size' must be >= 1"):
        await MemoryWindowNode().execute(_ctx_for(node), [Item()])


async def test_buffer_and_window_share_session_store() -> None:
    """Writing through buffer and reading through window sees one conversation."""
    state: dict[str, Any] = {}
    buffer_node = Node(
        id="n_buf", name="buf", type="weftlyflow.memory_buffer",
        parameters={
            "session_id": _SESSION,
            "operation": "append",
            "new_messages": [
                {"role": "user", "content": "a"},
                {"role": "user", "content": "b"},
                {"role": "user", "content": "c"},
            ],
        },
    )
    await MemoryBufferNode().execute(_ctx_for(buffer_node, static_data=state), [Item()])

    window_node = Node(
        id="n_win", name="win", type="weftlyflow.memory_window",
        parameters={"session_id": _SESSION, "operation": "load", "window_size": 2},
    )
    out = await MemoryWindowNode().execute(
        _ctx_for(window_node, static_data=state), [Item()],
    )
    assert [msg["content"] for msg in out[0][0].json["messages"]] == ["b", "c"]


# --- summary store helpers -------------------------------------------


def test_load_summary_empty_returns_blank_pair() -> None:
    summary, messages = load_summary({}, _SESSION)
    assert summary == "" and messages == []


def test_append_summary_under_limit_keeps_all() -> None:
    store: dict[str, Any] = {}
    summary, messages, overflow = append_summary_messages(
        store,
        _SESSION,
        [{"role": "user", "content": "1"}, {"role": "user", "content": "2"}],
        max_messages=5,
    )
    assert summary == ""
    assert [msg["content"] for msg in messages] == ["1", "2"]
    assert overflow == []


def test_append_summary_over_limit_returns_overflow_in_order() -> None:
    store: dict[str, Any] = {}
    for i in range(5):
        append_summary_messages(
            store,
            _SESSION,
            [{"role": "user", "content": str(i)}],
            max_messages=3,
        )
    # After 5 appends with cap 3, last call should have kept [2,3,4] and
    # flushed [1] (the [0] was already flushed two appends earlier).
    _, messages, _ = append_summary_messages(
        store,
        _SESSION,
        [{"role": "user", "content": "5"}],
        max_messages=3,
    )
    assert [msg["content"] for msg in messages] == ["3", "4", "5"]


def test_append_summary_rejects_non_positive_max() -> None:
    with pytest.raises(ValueError, match="max_messages must be >= 1"):
        append_summary_messages({}, _SESSION, [], max_messages=0)


def test_replace_summary_updates_summary_but_preserves_messages() -> None:
    store: dict[str, Any] = {}
    append_summary_messages(
        store, _SESSION, [{"role": "user", "content": "hi"}], max_messages=5,
    )
    summary, messages = replace_summary(store, _SESSION, "earlier: greeted")
    assert summary == "earlier: greeted"
    assert [msg["content"] for msg in messages] == ["hi"]


def test_clear_summary_drops_session() -> None:
    store: dict[str, Any] = {}
    append_summary_messages(
        store, _SESSION, [{"role": "user", "content": "hi"}], max_messages=5,
    )
    replace_summary(store, _SESSION, "rolled")
    clear_summary(store, _SESSION)
    assert load_summary(store, _SESSION) == ("", [])


def test_summary_and_buffer_use_different_namespaces() -> None:
    store: dict[str, Any] = {}
    append_history(store, _SESSION, [{"role": "user", "content": "buf"}])
    append_summary_messages(
        store, _SESSION, [{"role": "user", "content": "sum"}], max_messages=5,
    )
    assert MEMORY_NAMESPACE in store and MEMORY_SUMMARY_NAMESPACE in store
    # The buffer's view is unchanged by summary writes:
    assert load_history(store, _SESSION) == [{"role": "user", "content": "buf"}]


# --- MemorySummaryNode -----------------------------------------------


async def test_summary_load_on_empty_returns_blank_payload() -> None:
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={"session_id": _SESSION, "operation": "load"},
    )
    out = await MemorySummaryNode().execute(_ctx_for(node), [Item()])
    payload = out[0][0].json
    assert payload == {
        "session_id": _SESSION,
        "operation": "load",
        "summary": "",
        "messages": [],
        "count": 0,
        "pending_summary": [],
    }


async def test_summary_append_under_cap_keeps_all_and_no_pending() -> None:
    state: dict[str, Any] = {}
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={
            "session_id": _SESSION,
            "operation": "append",
            "max_messages": 5,
            "new_messages": [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
            ],
        },
    )
    out = await MemorySummaryNode().execute(_ctx_for(node, static_data=state), [Item()])
    payload = out[0][0].json
    assert payload["count"] == 2
    assert payload["pending_summary"] == []


async def test_summary_append_over_cap_emits_oldest_as_pending() -> None:
    state: dict[str, Any] = {}
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={
            "session_id": _SESSION,
            "operation": "append",
            "max_messages": 2,
            "new_messages": [
                {"role": "user", "content": "1"},
                {"role": "user", "content": "2"},
                {"role": "user", "content": "3"},
                {"role": "user", "content": "4"},
            ],
        },
    )
    out = await MemorySummaryNode().execute(_ctx_for(node, static_data=state), [Item()])
    payload = out[0][0].json
    assert [m["content"] for m in payload["messages"]] == ["3", "4"]
    assert [m["content"] for m in payload["pending_summary"]] == ["1", "2"]


async def test_summary_set_summary_replaces_text_without_touching_messages() -> None:
    state: dict[str, Any] = {}
    append_summary_messages(
        state, _SESSION, [{"role": "user", "content": "hi"}], max_messages=5,
    )
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={
            "session_id": _SESSION,
            "operation": "set_summary",
            "summary_text": "User greeted the assistant.",
        },
    )
    out = await MemorySummaryNode().execute(_ctx_for(node, static_data=state), [Item()])
    payload = out[0][0].json
    assert payload["summary"] == "User greeted the assistant."
    assert [m["content"] for m in payload["messages"]] == ["hi"]


async def test_summary_clear_drops_session() -> None:
    state: dict[str, Any] = {}
    append_summary_messages(
        state, _SESSION, [{"role": "user", "content": "hi"}], max_messages=5,
    )
    replace_summary(state, _SESSION, "rolled")
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={"session_id": _SESSION, "operation": "clear"},
    )
    await MemorySummaryNode().execute(_ctx_for(node, static_data=state), [Item()])
    assert load_summary(state, _SESSION) == ("", [])


async def test_summary_requires_session_id() -> None:
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={"session_id": "", "operation": "load"},
    )
    with pytest.raises(NodeExecutionError, match="'session_id' is required"):
        await MemorySummaryNode().execute(_ctx_for(node), [Item()])


async def test_summary_rejects_unknown_operation() -> None:
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={"session_id": _SESSION, "operation": "nuke"},
    )
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await MemorySummaryNode().execute(_ctx_for(node), [Item()])


async def test_summary_rejects_non_positive_max_messages() -> None:
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={
            "session_id": _SESSION,
            "operation": "append",
            "max_messages": 0,
        },
    )
    with pytest.raises(NodeExecutionError, match="'max_messages' must be >= 1"):
        await MemorySummaryNode().execute(_ctx_for(node), [Item()])


async def test_summary_rejects_non_list_new_messages() -> None:
    node = Node(
        id="n_sum", name="sum", type="weftlyflow.memory_summary",
        parameters={
            "session_id": _SESSION,
            "operation": "append",
            "max_messages": 5,
            "new_messages": "not-a-list",
        },
    )
    with pytest.raises(NodeExecutionError, match="must be a JSON array"):
        await MemorySummaryNode().execute(_ctx_for(node), [Item()])


async def test_summary_rolling_cycle_append_then_set_then_load() -> None:
    """End-to-end: overflow -> summarize (simulated) -> set -> later load."""
    state: dict[str, Any] = {}
    # Overfill to force overflow:
    await MemorySummaryNode().execute(
        _ctx_for(
            Node(
                id="n_sum", name="sum", type="weftlyflow.memory_summary",
                parameters={
                    "session_id": _SESSION,
                    "operation": "append",
                    "max_messages": 2,
                    "new_messages": [
                        {"role": "user", "content": "a"},
                        {"role": "assistant", "content": "b"},
                        {"role": "user", "content": "c"},
                    ],
                },
            ),
            static_data=state,
        ),
        [Item()],
    )
    # Caller computes a summary for the pending slice and commits it:
    await MemorySummaryNode().execute(
        _ctx_for(
            Node(
                id="n_sum", name="sum", type="weftlyflow.memory_summary",
                parameters={
                    "session_id": _SESSION,
                    "operation": "set_summary",
                    "summary_text": "User said hi; assistant replied.",
                },
            ),
            static_data=state,
        ),
        [Item()],
    )
    # A later load reflects both halves:
    out = await MemorySummaryNode().execute(
        _ctx_for(
            Node(
                id="n_sum", name="sum", type="weftlyflow.memory_summary",
                parameters={"session_id": _SESSION, "operation": "load"},
            ),
            static_data=state,
        ),
        [Item()],
    )
    payload = out[0][0].json
    assert payload["summary"] == "User said hi; assistant replied."
    assert [m["content"] for m in payload["messages"]] == ["b", "c"]
