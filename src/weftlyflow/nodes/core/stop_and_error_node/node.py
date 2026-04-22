"""Stop & Error node — halt the execution with a resolved error message.

Raises :class:`NodeExecutionError` directly so the engine's standard
error handling kicks in — ``continue_on_fail`` nodes downstream still
work because the engine wraps every node call in its try/except block.

The message is expression-capable: users can embed ``$json`` fields from
the item that triggered the stop.
"""

from __future__ import annotations

from typing import ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode


class StopAndErrorNode(BaseNode):
    """Raise :class:`NodeExecutionError` with a resolved message when reached."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.stop_and_error",
        version=1,
        display_name="Stop & Error",
        description="Halt the execution with a configurable error message.",
        icon="icons/stop.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[Port(name="main")],
        outputs=[],
        properties=[
            PropertySchema(
                name="message",
                display_name="Message",
                type="expression",
                required=True,
                default="Workflow stopped by Stop & Error node.",
            ),
            PropertySchema(
                name="code",
                display_name="Error code",
                type="string",
                default="stop_and_error",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Always raise — the return type is satisfied only by the exception."""
        sample = items[0] if items else Item()
        message = str(ctx.resolved_param("message", item=sample))
        code = str(ctx.param("code", "stop_and_error"))
        raise NodeExecutionError(
            message,
            node_id=ctx.node.id,
            original=None,
        ) from _code_marker(code)


class _StopAndErrorCodeError(Exception):
    """Sentinel exception carrying the user-supplied error code."""


def _code_marker(code: str) -> _StopAndErrorCodeError:
    return _StopAndErrorCodeError(code)
