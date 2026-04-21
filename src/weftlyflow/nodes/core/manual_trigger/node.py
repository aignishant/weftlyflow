"""Manual-trigger node — entry point for user-initiated runs.

Emits the executor's ``initial_items`` unchanged on its single ``main`` output
port. Workflows built in the editor typically wire this as the first node so
clicking "Execute" in the UI always has a deterministic seed.
"""

from __future__ import annotations

from typing import ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode


class ManualTriggerNode(BaseNode):
    """Emit the execution's initial items as the workflow's entry point."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.manual_trigger",
        version=1,
        display_name="Manual Trigger",
        description="Start the workflow on demand from the editor or the API.",
        icon="icons/manual-trigger.svg",
        category=NodeCategory.TRIGGER,
        group=["trigger"],
        inputs=[],
        outputs=[Port(name="main")],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Forward the seeded items on the single ``main`` output port."""
        del ctx  # Manual trigger ignores node parameters and context state.
        return [list(items)]
