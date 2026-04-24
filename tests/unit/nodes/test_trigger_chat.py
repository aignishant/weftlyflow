"""Unit tests for the ``trigger_chat`` node."""

from __future__ import annotations

from typing import Any

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.trigger_chat import ChatTriggerNode


def _ctx_for(
    node: Node,
    *,
    static_data: dict[str, Any] | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="trigger",
        node=node,
        inputs={"main": []},
        static_data=static_data if static_data is not None else {},
    )


def _default_node(**params: Any) -> Node:
    return Node(
        id="t",
        name="t",
        type="weftlyflow.trigger_chat",
        parameters=params,
    )


async def test_unwraps_webhook_request_body_into_chat_shape() -> None:
    node = _default_node()
    seed = Item(
        json={
            "request": {
                "method": "POST",
                "path": "chat/room-1",
                "body": {
                    "message": "hello there",
                    "session_id": "sess_42",
                    "user_id": "user_7",
                    "history": [{"role": "user", "content": "hi"}],
                },
            }
        }
    )

    out = await ChatTriggerNode().execute(_ctx_for(node), [seed])

    payload = out[0][0].json
    assert payload["message"] == "hello there"
    assert payload["session_id"] == "sess_42"
    assert payload["user_id"] == "user_7"
    assert payload["history"] == [{"role": "user", "content": "hi"}]
    assert payload["raw"] == seed.json["request"]["body"]


async def test_falls_back_to_flat_payload_when_no_request_wrapper() -> None:
    node = _default_node()
    seed = Item(json={"message": "direct", "session_id": "s1"})

    out = await ChatTriggerNode().execute(_ctx_for(node), [seed])

    payload = out[0][0].json
    assert payload["message"] == "direct"
    assert payload["session_id"] == "s1"
    assert payload["user_id"] == ""
    assert payload["history"] == []
    assert payload["raw"] == {"message": "direct", "session_id": "s1"}


async def test_custom_field_names_are_honored() -> None:
    node = _default_node(
        message_field="text",
        session_id_field="thread",
        user_id_field="author",
        history_field="turns",
    )
    seed = Item(
        json={
            "text": "renamed",
            "thread": "t1",
            "author": "alice",
            "turns": [{"role": "assistant", "content": "ok"}],
        }
    )

    out = await ChatTriggerNode().execute(_ctx_for(node), [seed])

    payload = out[0][0].json
    assert payload["message"] == "renamed"
    assert payload["session_id"] == "t1"
    assert payload["user_id"] == "alice"
    assert payload["history"] == [{"role": "assistant", "content": "ok"}]


async def test_missing_fields_default_to_empty_values() -> None:
    node = _default_node()
    seed = Item(json={"request": {"body": {}}})

    out = await ChatTriggerNode().execute(_ctx_for(node), [seed])

    payload = out[0][0].json
    assert payload["message"] == ""
    assert payload["session_id"] == ""
    assert payload["user_id"] == ""
    assert payload["history"] == []
    assert payload["raw"] == {}


async def test_non_string_fields_are_coerced_to_strings() -> None:
    node = _default_node()
    seed = Item(
        json={"request": {"body": {"message": 42, "session_id": None}}}
    )

    out = await ChatTriggerNode().execute(_ctx_for(node), [seed])

    payload = out[0][0].json
    assert payload["message"] == "42"
    assert payload["session_id"] == ""


async def test_history_drops_non_dict_entries() -> None:
    node = _default_node()
    seed = Item(
        json={
            "request": {
                "body": {
                    "message": "x",
                    "history": [{"role": "user"}, "not-a-dict", 7, {"role": "bot"}],
                }
            }
        }
    )

    out = await ChatTriggerNode().execute(_ctx_for(node), [seed])

    assert out[0][0].json["history"] == [{"role": "user"}, {"role": "bot"}]


async def test_emits_one_envelope_per_input_item() -> None:
    node = _default_node()
    seeds = [
        Item(json={"message": "first", "session_id": "s1"}),
        Item(json={"message": "second", "session_id": "s2"}),
    ]

    out = await ChatTriggerNode().execute(_ctx_for(node), seeds)

    assert len(out) == 1
    assert [item.json["message"] for item in out[0]] == ["first", "second"]
    assert [item.json["session_id"] for item in out[0]] == ["s1", "s2"]
