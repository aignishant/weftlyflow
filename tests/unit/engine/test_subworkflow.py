"""End-to-end tests for the InlineSubWorkflowRunner + function_call wiring.

Each test builds two workflows (parent + child), registers them with a
dict-backed loader, and asserts that the parent's final items come from
the child's terminal node.
"""

from __future__ import annotations

import pytest

from tests.unit.engine.conftest import build_workflow, connect, make_node
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Workflow
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.engine.subworkflow import (
    InlineSubWorkflowRunner,
    SubWorkflowNotFoundError,
    SubWorkflowProjectMismatchError,
)
from weftlyflow.nodes.registry import NodeRegistry


def _registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.load_builtins()
    return reg


def _child_workflow(*, project_id: str = "pr_test") -> Workflow:
    """Child: Set(value={"from": "child"}) → terminal."""
    set_node = make_node(
        node_type="weftlyflow.set",
        parameters={
            "mode": "replace",
            "assignments": [{"name": "from", "value": "child"}],
        },
    )
    return build_workflow([set_node], [], project_id=project_id)


async def test_function_call_runs_child_and_returns_its_items() -> None:
    registry = _registry()
    child = _child_workflow()

    async def loader(workflow_id: str, project_id: str) -> Workflow | None:
        if workflow_id == "wf_child":
            return child
        return None

    runner = InlineSubWorkflowRunner(registry=registry, loader=loader)

    fn = make_node(
        node_type="weftlyflow.function_call",
        parameters={"workflow_id": "wf_child", "forward": "main"},
    )
    parent = build_workflow([fn], [], project_id=child.project_id)
    executor = WorkflowExecutor(registry, sub_workflow_runner=runner)

    execution = await executor.run(parent, initial_items=[Item()])

    assert execution.status == "success"
    fn_run = execution.run_data.per_node[fn.id][-1]
    assert [it.json for it in fn_run.items[0]] == [{"from": "child"}]


async def test_function_call_forwards_parent_items_as_initial() -> None:
    registry = _registry()
    # Child: NoOp passes items through — so whatever we forward becomes output.
    noop = make_node(node_type="weftlyflow.no_op")
    child = build_workflow([noop], [])

    async def loader(workflow_id: str, project_id: str) -> Workflow | None:
        return child if workflow_id == "wf_child" else None

    runner = InlineSubWorkflowRunner(registry=registry, loader=loader)

    fn = make_node(
        node_type="weftlyflow.function_call",
        parameters={"workflow_id": "wf_child", "forward": "main"},
    )
    parent = build_workflow([fn], [], project_id=child.project_id)
    executor = WorkflowExecutor(registry, sub_workflow_runner=runner)

    seed = [Item(json={"k": 1}), Item(json={"k": 2})]
    execution = await executor.run(parent, initial_items=seed)

    fn_run = execution.run_data.per_node[fn.id][-1]
    assert [it.json for it in fn_run.items[0]] == [{"k": 1}, {"k": 2}]


async def test_function_call_inside_a_chain_feeds_downstream() -> None:
    registry = _registry()
    child = _child_workflow()

    async def loader(workflow_id: str, project_id: str) -> Workflow | None:
        return child if workflow_id == "wf_child" else None

    runner = InlineSubWorkflowRunner(registry=registry, loader=loader)

    fn = make_node(
        node_type="weftlyflow.function_call",
        parameters={"workflow_id": "wf_child", "forward": "main"},
    )
    enrich = make_node(
        node_type="weftlyflow.set",
        parameters={
            "mode": "merge",
            "assignments": [{"name": "tagged", "value": True}],
        },
    )
    parent = build_workflow(
        [fn, enrich], [connect(fn, enrich)], project_id=child.project_id,
    )
    executor = WorkflowExecutor(registry, sub_workflow_runner=runner)

    execution = await executor.run(parent, initial_items=[Item()])
    enrich_run = execution.run_data.per_node[enrich.id][-1]
    assert enrich_run.items[0][0].json == {"from": "child", "tagged": True}


async def test_missing_workflow_raises() -> None:
    registry = _registry()

    async def loader(workflow_id: str, project_id: str) -> Workflow | None:
        return None

    runner = InlineSubWorkflowRunner(registry=registry, loader=loader)

    with pytest.raises(SubWorkflowNotFoundError):
        await runner.run(
            workflow_id="wf_missing",
            items=[],
            parent_execution_id="ex_parent",
            project_id="pr_test",
        )


async def test_cross_project_raises() -> None:
    registry = _registry()
    child = _child_workflow(project_id="pr_other")

    async def loader(workflow_id: str, project_id: str) -> Workflow | None:
        return child

    runner = InlineSubWorkflowRunner(registry=registry, loader=loader)

    with pytest.raises(SubWorkflowProjectMismatchError):
        await runner.run(
            workflow_id="wf_child",
            items=[],
            parent_execution_id="ex_parent",
            project_id="pr_test",
        )
