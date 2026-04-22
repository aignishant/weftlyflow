"""Split In Batches node — emit input items in fixed-size chunks.

The node has two output ports:

* ``batch`` — the next slice of ``batch_size`` items. Empty on the call that
  exhausts the input.
* ``done`` — receives the full input list on the call that exhausts it, so
  downstream "after the loop" logic can trigger once.

A cursor is kept in :attr:`ExecutionContext.static_data` under a
node-scoped key so repeated invocations (e.g. inside a loop or on
subsequent trigger fires) step through the input list. ``reset=True`` sends
the cursor back to 0 before slicing.

The node is designed to be harmless when called only once: the first call
emits the first batch on ``batch``; downstream logic can then fan-out or
loop back depending on the workflow topology.
"""

from __future__ import annotations

from typing import ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode

_PORT_BATCH: str = "batch"
_PORT_DONE: str = "done"
_DEFAULT_BATCH_SIZE: int = 10
_MIN_BATCH_SIZE: int = 1


class SplitInBatchesNode(BaseNode):
    """Emit the next slice of ``batch_size`` items on the ``batch`` port."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.split_in_batches",
        version=1,
        display_name="Split In Batches",
        description="Iterate a list of items in fixed-size chunks across invocations.",
        icon="icons/split-in-batches.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[Port(name="main")],
        outputs=[
            Port(name=_PORT_BATCH, index=0, display_name="Batch"),
            Port(name=_PORT_DONE, index=1, display_name="Done"),
        ],
        properties=[
            PropertySchema(
                name="batch_size",
                display_name="Batch size",
                type="number",
                default=_DEFAULT_BATCH_SIZE,
                required=True,
                description="Number of items to emit per call on the 'batch' port.",
            ),
            PropertySchema(
                name="reset",
                display_name="Reset cursor",
                type="boolean",
                default=False,
                description="Start the iteration from the beginning of the input list.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Advance the cursor and emit the next batch (or the done signal)."""
        batch_size = _coerce_batch_size(ctx.param("batch_size", _DEFAULT_BATCH_SIZE))
        reset = bool(ctx.param("reset", False))
        state_key = _state_key(ctx.node.id)

        if reset or state_key not in ctx.static_data:
            ctx.static_data[state_key] = 0
        cursor = int(ctx.static_data[state_key])

        if cursor >= len(items):
            # Iteration complete — reset for the next run, fire the done port.
            ctx.static_data[state_key] = 0
            return [[], list(items)]

        batch = items[cursor : cursor + batch_size]
        ctx.static_data[state_key] = cursor + batch_size
        return [batch, []]


def _state_key(node_id: str) -> str:
    return f"split_in_batches:{node_id}:cursor"


def _coerce_batch_size(raw: object) -> int:
    if not isinstance(raw, (int, float, str)):
        msg = "Split In Batches: 'batch_size' must be an integer"
        raise ValueError(msg)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Split In Batches: 'batch_size' must be an integer"
        raise ValueError(msg) from exc
    if value < _MIN_BATCH_SIZE:
        msg = f"Split In Batches: 'batch_size' must be >= {_MIN_BATCH_SIZE}"
        raise ValueError(msg)
    return value
