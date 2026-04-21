"""No-op node — items in, same items out.

Useful as:
    * a documentation anchor in a complex graph,
    * a placeholder while iterating on a workflow,
    * a test double in unit tests for the engine.
"""

from __future__ import annotations

from typing import ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode


class NoOpNode(BaseNode):
    """Return the input items unchanged."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.no_op",
        version=1,
        display_name="No Op",
        description="Pass items through unchanged.",
        icon="icons/no-op.svg",
        category=NodeCategory.CORE,
        group=["utility"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Return the same items on the single ``main`` port."""
        del ctx
        return [list(items)]
