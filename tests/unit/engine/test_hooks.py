"""Tests for :class:`weftlyflow.engine.hooks.LifecycleHooks` invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.unit.engine.conftest import build_workflow, connect, make_node, one_item
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.engine.hooks import NullHooks
from weftlyflow.nodes.registry import NodeRegistry


@dataclass
class RecordingHooks(NullHooks):
    """Appends an event name for each hook call — makes ordering explicit."""

    events: list[tuple[str, str]] = field(default_factory=list)

    async def on_execution_start(self, ctx: Any) -> None:
        self.events.append(("execution_start", ""))

    async def on_execution_end(self, ctx: Any, execution: Any) -> None:
        self.events.append(("execution_end", execution.status))

    async def on_node_start(self, ctx: Any, node: Any) -> None:
        self.events.append(("node_start", node.name))

    async def on_node_end(self, ctx: Any, node: Any, run_data: Any) -> None:
        self.events.append(("node_end", node.name))

    async def on_node_error(self, ctx: Any, node: Any, error: BaseException) -> None:
        self.events.append(("node_error", node.name))


async def test_hook_ordering_on_successful_run(loaded_registry: NodeRegistry) -> None:
    hooks = RecordingHooks()
    a = make_node(node_type="weftlyflow.manual_trigger", name="A")
    b = make_node(node_type="weftlyflow.no_op", name="B")
    wf = build_workflow([a, b], [connect(a, b)])
    await WorkflowExecutor(loaded_registry, hooks=hooks).run(wf, initial_items=one_item())

    names = [evt[0] for evt in hooks.events]
    assert names[0] == "execution_start"
    assert names[-1] == "execution_end"
    # Each node has exactly one start/end pair:
    for node_name in ("A", "B"):
        assert ("node_start", node_name) in hooks.events
        assert ("node_end", node_name) in hooks.events

    # node_start for a node always precedes its node_end:
    assert hooks.events.index(("node_start", "A")) < hooks.events.index(("node_end", "A"))
