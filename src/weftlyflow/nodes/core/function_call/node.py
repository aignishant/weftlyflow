"""Function Call node — invoke another workflow as a sub-execution.

The node delegates to the :class:`SubWorkflowRunner` attached to the
current :class:`ExecutionContext`. This keeps the node decoupled from
whichever runtime (inline worker, Celery task, future remote dispatch)
actually owns execution scheduling.

Parameters:

* ``workflow_id`` — target workflow (resolved per item so a single node
  can fan out to multiple child workflows).
* ``forward`` — one of:
    - ``main`` (default): pass through the items arriving on ``main``;
    - ``none``: call with an empty item list.

The child workflow's final items become this node's output, so a
Function Call followed by a Set node reads just like a normal linear
branch.
"""

from __future__ import annotations

from typing import ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode

_FORWARD_MAIN: str = "main"
_FORWARD_NONE: str = "none"
_FORWARD_MODES: tuple[str, ...] = (_FORWARD_MAIN, _FORWARD_NONE)


class FunctionCallNode(BaseNode):
    """Execute ``workflow_id`` as a sub-workflow and emit its items."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.function_call",
        version=1,
        display_name="Function Call",
        description="Run another workflow and emit its output as this node's output.",
        icon="icons/function-call.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="workflow_id",
                display_name="Workflow ID",
                type="string",
                default="",
                required=True,
                description="Target workflow identifier. Supports {{ expressions }}.",
            ),
            PropertySchema(
                name="forward",
                display_name="Forward items",
                type="options",
                default=_FORWARD_MAIN,
                options=[
                    PropertyOption(value=_FORWARD_MAIN, label="Main input"),
                    PropertyOption(value=_FORWARD_NONE, label="None (empty)"),
                ],
                description="Whether to forward this node's input to the child workflow.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Delegate to the configured sub-workflow runner and return its output."""
        if ctx.sub_workflow_runner is None:
            msg = (
                "Function Call: ExecutionContext has no sub_workflow_runner — "
                "the runtime must wire one before this node can execute."
            )
            raise ValueError(msg)

        workflow_id = str(ctx.resolved_param("workflow_id") or "").strip()
        if not workflow_id:
            msg = "Function Call: 'workflow_id' is required"
            raise ValueError(msg)

        forward = str(ctx.param("forward", _FORWARD_MAIN))
        if forward not in _FORWARD_MODES:
            msg = f"Function Call: unknown forward mode {forward!r}"
            raise ValueError(msg)

        payload = list(items) if forward == _FORWARD_MAIN else []
        result = await ctx.sub_workflow_runner.run(
            workflow_id=workflow_id,
            items=payload,
            parent_execution_id=ctx.execution_id,
            project_id=ctx.workflow.project_id,
        )
        return [list(result)]
