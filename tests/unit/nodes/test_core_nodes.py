"""Per-node unit tests for the Phase-1 built-in core nodes."""

from __future__ import annotations

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.core.code import CodeNode
from weftlyflow.nodes.core.if_node import IfNode
from weftlyflow.nodes.core.manual_trigger import ManualTriggerNode
from weftlyflow.nodes.core.no_op import NoOpNode
from weftlyflow.nodes.core.set_node import SetNode


def _ctx_for(node: Node, inputs: list[Item] | None = None) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": list(inputs or [])},
    )


async def test_manual_trigger_passes_initial_items_through():
    node = Node(id="node_1", name="t", type="weftlyflow.manual_trigger")
    items = [Item(json={"x": 1})]
    out = await ManualTriggerNode().execute(_ctx_for(node, items), items)
    assert out == [items]


async def test_no_op_returns_same_items():
    node = Node(id="node_1", name="n", type="weftlyflow.no_op")
    items = [Item(json={"a": 1}), Item(json={"a": 2})]
    out = await NoOpNode().execute(_ctx_for(node, items), items)
    assert out[0] == items


async def test_set_node_adds_and_removes_fields():
    node = Node(
        id="node_1",
        name="s",
        type="weftlyflow.set",
        parameters={
            "assignments": [
                {"name": "tagged", "value": True},
                {"name": "nested.key", "value": "v"},
            ],
            "removals": ["drop_me"],
            "keep_only_set": False,
        },
    )
    items = [Item(json={"drop_me": "gone", "keep": 1})]
    out = await SetNode().execute(_ctx_for(node, items), items)
    [result] = out[0]
    assert result.json == {"keep": 1, "tagged": True, "nested": {"key": "v"}}


async def test_set_node_keep_only_projects_to_assignments():
    node = Node(
        id="node_1",
        name="s",
        type="weftlyflow.set",
        parameters={
            "assignments": [{"name": "onlyme", "value": 1}],
            "removals": [],
            "keep_only_set": True,
        },
    )
    items = [Item(json={"a": 1, "b": 2})]
    out = await SetNode().execute(_ctx_for(node, items), items)
    [result] = out[0]
    assert result.json == {"onlyme": 1}


async def test_if_node_splits_items_into_two_ports():
    node = Node(
        id="node_1",
        name="i",
        type="weftlyflow.if",
        parameters={"field": "n", "operator": "greater_than", "value": 5},
    )
    items = [Item(json={"n": 1}), Item(json={"n": 10}), Item(json={"n": 6})]
    out = await IfNode().execute(_ctx_for(node, items), items)
    assert [item.json["n"] for item in out[0]] == [10, 6]
    assert [item.json["n"] for item in out[1]] == [1]


async def test_if_node_missing_field_parameter_raises():
    node = Node(
        id="node_1",
        name="i",
        type="weftlyflow.if",
        parameters={"field": "", "operator": "equals", "value": 1},
    )
    with pytest.raises(ValueError):
        await IfNode().execute(_ctx_for(node, []), [])


async def test_if_node_unknown_operator_raises():
    node = Node(
        id="node_1",
        name="i",
        type="weftlyflow.if",
        parameters={"field": "n", "operator": "bogus", "value": 1},
    )
    with pytest.raises(ValueError):
        await IfNode().execute(_ctx_for(node, []), [])


async def test_code_node_is_identity_for_empty_snippet():
    """Empty snippets pass items through — the legitimate no-op path."""
    node = Node(
        id="node_1",
        name="c",
        type="weftlyflow.code",
        parameters={"code": "", "mode": "run_once_for_all"},
    )
    items = [Item(json={"v": 1})]
    out = await CodeNode().execute(_ctx_for(node, items), items)
    assert out[0] == items


async def test_code_node_refuses_non_empty_snippet_until_sandbox_lands():
    """Non-empty snippets must raise until the subprocess sandbox exists.

    Silently discarding user code would bite the operator the moment a
    real sandbox shipped — every saved snippet would suddenly start
    executing. Loud failure is the safer default.
    """
    from weftlyflow.domain.errors import NodeExecutionError

    node = Node(
        id="node_1",
        name="c",
        type="weftlyflow.code",
        parameters={
            "code": "raise Exception('should not run until sandbox lands')",
            "mode": "run_once_for_all",
        },
    )
    items = [Item(json={"v": 1})]
    with pytest.raises(NodeExecutionError):
        await CodeNode().execute(_ctx_for(node, items), items)
