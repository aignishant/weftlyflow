"""Phase-1 acceptance test — the 5-node workflow promised in the spec.

Shape::

    ManualTrigger -> Set -> If --true--> NoOp
                              \\
                               --false--> Code

The assertions walk the resulting :class:`Execution` and verify:

1. All five nodes produced run-data,
2. Set added the expected field to every item,
3. Adults were routed through the "true" branch (NoOp),
4. Minors were routed through the "false" branch (Code),
5. Overall execution status is ``success``.
"""

from __future__ import annotations

from tests.unit.engine.conftest import build_workflow, connect, make_node
from weftlyflow.domain.execution import Item
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.nodes.core.code.node import CodeNode
from weftlyflow.nodes.registry import NodeRegistry


async def test_five_node_workflow_runs_end_to_end(loaded_registry: NodeRegistry) -> None:
    # Code node is gated behind a settings flag (off by default); register
    # it explicitly for this acceptance test so the false branch has a
    # real destination. The node runs as identity for empty snippets.
    loaded_registry.register(CodeNode)
    trigger = make_node(node_type="weftlyflow.manual_trigger", name="Trigger")
    setter = make_node(
        node_type="weftlyflow.set",
        name="Setter",
        parameters={
            "assignments": [{"name": "tagged", "value": True}],
            "removals": [],
            "keep_only_set": False,
        },
    )
    decision = make_node(
        node_type="weftlyflow.if",
        name="Adult?",
        parameters={
            "field": "age",
            "operator": "greater_than_or_equal",
            "value": 18,
        },
    )
    true_branch = make_node(node_type="weftlyflow.no_op", name="Adult-Route")
    false_branch = make_node(node_type="weftlyflow.code", name="Minor-Route")

    wf = build_workflow(
        [trigger, setter, decision, true_branch, false_branch],
        [
            connect(trigger, setter),
            connect(setter, decision),
            connect(decision, true_branch, source_port="true", source_index=0),
            connect(decision, false_branch, source_port="false", source_index=1),
        ],
        name="five-node-acceptance",
    )

    items = [Item(json={"age": 30}), Item(json={"age": 10}), Item(json={"age": 21})]
    execution = await WorkflowExecutor(loaded_registry).run(wf, initial_items=items)

    assert execution.status == "success"
    # 1. all five nodes produced run-data
    assert set(execution.run_data.per_node) == {
        trigger.id, setter.id, decision.id, true_branch.id, false_branch.id,
    }

    # 2. Set added `tagged=True` to every item that flowed through
    setter_items = execution.run_data.per_node[setter.id][0].items[0]
    assert all(item.json.get("tagged") is True for item in setter_items)

    # 3. Adults routed through the true branch
    adults = execution.run_data.per_node[true_branch.id][0].items[0]
    assert [item.json["age"] for item in adults] == [30, 21]
    assert all(item.json["tagged"] is True for item in adults)

    # 4. Minors routed through the false branch (Code is identity in Phase 1)
    minors = execution.run_data.per_node[false_branch.id][0].items[0]
    assert [item.json["age"] for item in minors] == [10]
    assert all(item.json["tagged"] is True for item in minors)
