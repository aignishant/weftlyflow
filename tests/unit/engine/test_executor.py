"""Tests for :class:`weftlyflow.engine.executor.WorkflowExecutor`."""

from __future__ import annotations

import pytest

from tests.unit.engine.conftest import build_workflow, connect, make_node, one_item
from weftlyflow.domain.execution import Item
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.core.manual_trigger import ManualTriggerNode
from weftlyflow.nodes.core.no_op import NoOpNode
from weftlyflow.nodes.registry import NodeRegistry


async def test_happy_path_single_node(loaded_registry: NodeRegistry) -> None:
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    wf = build_workflow([trigger], [])
    execution = await WorkflowExecutor(loaded_registry).run(
        wf, initial_items=one_item({"k": 1}),
    )
    assert execution.status == "success"
    assert execution.run_data.per_node[trigger.id][0].items[0][0].json == {"k": 1}


async def test_linear_chain_propagates_items(loaded_registry: NodeRegistry) -> None:
    a = make_node(node_type="weftlyflow.manual_trigger")
    b = make_node(node_type="weftlyflow.no_op")
    c = make_node(node_type="weftlyflow.no_op")
    wf = build_workflow([a, b, c], [connect(a, b), connect(b, c)])
    execution = await WorkflowExecutor(loaded_registry).run(
        wf, initial_items=one_item({"n": 7}),
    )
    assert execution.status == "success"
    assert set(execution.run_data.per_node) == {a.id, b.id, c.id}
    assert execution.run_data.per_node[c.id][0].items[0][0].json == {"n": 7}


async def test_if_branching_routes_to_correct_port(loaded_registry: NodeRegistry) -> None:
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    decision = make_node(
        node_type="weftlyflow.if",
        parameters={"field": "age", "operator": "greater_than_or_equal", "value": 18},
    )
    adult = make_node(node_type="weftlyflow.no_op", name="Adult")
    minor = make_node(node_type="weftlyflow.no_op", name="Minor")
    wf = build_workflow(
        [trigger, decision, adult, minor],
        [
            connect(trigger, decision),
            connect(decision, adult, source_port="true", source_index=0),
            connect(decision, minor, source_port="false", source_index=1),
        ],
    )
    execution = await WorkflowExecutor(loaded_registry).run(
        wf,
        initial_items=[Item(json={"age": 30}), Item(json={"age": 12})],
    )
    assert execution.status == "success"
    adult_items = execution.run_data.per_node[adult.id][0].items[0]
    minor_items = execution.run_data.per_node[minor.id][0].items[0]
    assert [item.json["age"] for item in adult_items] == [30]
    assert [item.json["age"] for item in minor_items] == [12]


async def test_disabled_node_passes_inputs_through(loaded_registry: NodeRegistry) -> None:
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    disabled = make_node(node_type="weftlyflow.no_op", disabled=True)
    tail = make_node(node_type="weftlyflow.no_op")
    wf = build_workflow(
        [trigger, disabled, tail],
        [connect(trigger, disabled), connect(disabled, tail)],
    )
    execution = await WorkflowExecutor(loaded_registry).run(
        wf, initial_items=one_item({"x": 1}),
    )
    assert execution.run_data.per_node[disabled.id][0].status == "disabled"
    assert execution.run_data.per_node[tail.id][0].items[0][0].json == {"x": 1}


async def test_pin_data_short_circuits_node() -> None:
    registry = NodeRegistry()
    registry.load_builtins()
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    pinned = make_node(node_type="weftlyflow.no_op")
    wf = build_workflow([trigger, pinned], [connect(trigger, pinned)])
    wf.pin_data[pinned.id] = [{"pinned": True}]
    execution = await WorkflowExecutor(registry).run(wf, initial_items=one_item())
    assert execution.run_data.per_node[pinned.id][0].items[0][0].json == {"pinned": True}


async def test_continue_on_fail_emits_error_item(loaded_registry: NodeRegistry) -> None:
    """A raising node with continue_on_fail True emits an error item instead of halting."""

    class BoomNode(BaseNode):
        """Test double that always raises."""

        spec = NoOpNode.spec  # reuse the spec; registry keys by (type, version)

        async def execute(self, ctx, items):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    registry = NodeRegistry()
    registry.register(ManualTriggerNode)
    registry.register(BoomNode, replace=True)

    trigger = make_node(node_type="weftlyflow.manual_trigger")
    boom = make_node(node_type="weftlyflow.no_op", continue_on_fail=True)
    wf = build_workflow([trigger, boom], [connect(trigger, boom)])
    execution = await WorkflowExecutor(registry).run(wf, initial_items=one_item())
    assert execution.status == "success"
    boom_items = execution.run_data.per_node[boom.id][0].items[0]
    assert boom_items[0].error is not None
    assert boom_items[0].error.message == "boom"


async def test_throwing_node_aborts_execution() -> None:
    """Without continue_on_fail, a raise stops the run with status=error."""

    class BoomNode(BaseNode):
        spec = NoOpNode.spec

        async def execute(self, ctx, items):  # type: ignore[no-untyped-def]
            raise RuntimeError("stop")

    registry = NodeRegistry()
    registry.register(ManualTriggerNode)
    registry.register(BoomNode, replace=True)

    trigger = make_node(node_type="weftlyflow.manual_trigger")
    boom = make_node(node_type="weftlyflow.no_op")
    tail = make_node(node_type="weftlyflow.no_op")
    wf = build_workflow(
        [trigger, boom, tail], [connect(trigger, boom), connect(boom, tail)],
    )
    execution = await WorkflowExecutor(registry).run(wf, initial_items=one_item())
    assert execution.status == "error"
    assert boom.id in execution.run_data.per_node
    # Downstream node must not have run:
    assert tail.id not in execution.run_data.per_node


async def test_unknown_node_type_raises(loaded_registry: NodeRegistry) -> None:
    ghost = make_node(node_type="weftlyflow.does_not_exist")
    wf = build_workflow([ghost], [])
    execution = await WorkflowExecutor(loaded_registry).run(wf, initial_items=one_item())
    assert execution.status == "error"


async def test_execution_id_override_is_respected(loaded_registry: NodeRegistry) -> None:
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    wf = build_workflow([trigger], [])
    execution = await WorkflowExecutor(loaded_registry).run(
        wf, initial_items=one_item(), execution_id="ex_custom_id",
    )
    assert execution.id == "ex_custom_id"


@pytest.mark.parametrize("mode", ["manual", "trigger", "webhook", "test"])
async def test_modes_are_preserved(loaded_registry: NodeRegistry, mode: str) -> None:
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    wf = build_workflow([trigger], [])
    execution = await WorkflowExecutor(loaded_registry).run(wf, initial_items=one_item(), mode=mode)  # type: ignore[arg-type]
    assert execution.mode == mode
