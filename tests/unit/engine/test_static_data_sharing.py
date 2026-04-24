"""Tests that ``ExecutionContext.static_data`` is shared across one run.

The engine seeds ``RunState.static_data`` from
:attr:`weftlyflow.domain.workflow.Workflow.static_data` and threads the
*same* mutable dict through every :class:`ExecutionContext` — start hook,
each node, and the end hook. That gives session-keyed nodes (memory,
rate limiters, dedup counters) a place to stash state that's visible to
every downstream reader in the same run, without touching the caller's
workflow snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from tests.unit.engine.conftest import build_workflow, connect, make_node, one_item
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.engine.hooks import NullHooks
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.core.manual_trigger import ManualTriggerNode
from weftlyflow.nodes.registry import NodeRegistry


class _WriterNode(BaseNode):
    """Test double that writes a sentinel key into ``ctx.static_data``."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="tests.static_writer",
        version=1,
        display_name="Writer",
        description="test",
        icon="x",
        category=NodeCategory.CORE,
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        ctx.static_data["counter"] = ctx.static_data.get("counter", 0) + 1
        ctx.static_data.setdefault("trail", []).append("writer")
        return [items or [Item()]]


class _ReaderNode(BaseNode):
    """Test double that emits an item echoing whatever ``static_data`` holds."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="tests.static_reader",
        version=1,
        display_name="Reader",
        description="test",
        icon="x",
        category=NodeCategory.CORE,
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        return [[Item(json=dict(ctx.static_data))]]


@dataclass
class _StaticDataCapturingHooks(NullHooks):
    """Records the ``static_data`` identity at lifecycle boundaries."""

    start_id: int | None = None
    end_id: int | None = None
    end_snapshot: dict[str, Any] = field(default_factory=dict)

    async def on_execution_start(self, ctx: Any) -> None:
        self.start_id = id(ctx.static_data)

    async def on_execution_end(self, ctx: Any, execution: Any) -> None:
        self.end_id = id(ctx.static_data)
        self.end_snapshot = dict(ctx.static_data)


def _registry_with(*node_classes: type[BaseNode]) -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(ManualTriggerNode)
    for cls in node_classes:
        registry.register(cls)
    return registry


async def test_writer_then_reader_share_one_static_data_dict() -> None:
    """A write from node A is visible to node B in the same run."""
    registry = _registry_with(_WriterNode, _ReaderNode)
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    writer = make_node(node_type="tests.static_writer")
    reader = make_node(node_type="tests.static_reader")
    wf = build_workflow(
        [trigger, writer, reader],
        [connect(trigger, writer), connect(writer, reader)],
    )

    execution = await WorkflowExecutor(registry).run(wf, initial_items=one_item())

    assert execution.status == "success"
    payload = execution.run_data.per_node[reader.id][0].items[0][0].json
    assert payload["counter"] == 1
    assert payload["trail"] == ["writer"]


async def test_workflow_seeded_static_data_reaches_first_node() -> None:
    """``Workflow.static_data`` seeds the run; nodes read it on entry."""
    registry = _registry_with(_ReaderNode)
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    reader = make_node(node_type="tests.static_reader")
    wf = build_workflow([trigger, reader], [connect(trigger, reader)])
    wf.static_data["seeded"] = "yes"

    execution = await WorkflowExecutor(registry).run(wf, initial_items=one_item())

    payload = execution.run_data.per_node[reader.id][0].items[0][0].json
    assert payload == {"seeded": "yes"}


async def test_seed_dict_is_defensively_copied_from_workflow() -> None:
    """Mutating ``static_data`` mid-run must not touch the caller's workflow."""
    registry = _registry_with(_WriterNode)
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    writer = make_node(node_type="tests.static_writer")
    wf = build_workflow([trigger, writer], [connect(trigger, writer)])
    wf.static_data["counter"] = 41

    await WorkflowExecutor(registry).run(wf, initial_items=one_item())

    assert wf.static_data == {"counter": 41}


async def test_lifecycle_hooks_see_same_dict_as_nodes() -> None:
    """Start and end hooks observe the same ``static_data`` mutations as nodes."""
    registry = _registry_with(_WriterNode)
    hooks = _StaticDataCapturingHooks()
    trigger = make_node(node_type="weftlyflow.manual_trigger")
    writer = make_node(node_type="tests.static_writer")
    wf = build_workflow([trigger, writer], [connect(trigger, writer)])

    await WorkflowExecutor(registry, hooks=hooks).run(wf, initial_items=one_item())

    assert hooks.start_id is not None
    assert hooks.start_id == hooks.end_id
    assert hooks.end_snapshot == {"counter": 1, "trail": ["writer"]}
