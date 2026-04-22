"""Merge node — combine items arriving on two input ports.

Three modes:

* ``append`` — output = input_a + input_b.
* ``combine_by_position`` — pair items by list index; i-th output =
  ``{**a[i].json, **b[i].json}``. Unmatched tails are dropped.
* ``combine_by_key`` — inner-join on a shared key (like SQL inner join on
  ``a.<key> = b.<key>``).

Both inputs are declared as dedicated ports (``main`` and ``input_2``).
Upstream connections set their ``target_port`` accordingly; the engine
delivers each bucket to the matching input entry in
:attr:`ExecutionContext.inputs`.
"""

from __future__ import annotations

from typing import Any, ClassVar

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
from weftlyflow.nodes.utils import get_path

_MODE_APPEND: str = "append"
_MODE_BY_POSITION: str = "combine_by_position"
_MODE_BY_KEY: str = "combine_by_key"
_MODES: tuple[str, ...] = (_MODE_APPEND, _MODE_BY_POSITION, _MODE_BY_KEY)
_INPUT_A: str = "main"
_INPUT_B: str = "input_2"


class MergeNode(BaseNode):
    """Combine two input streams into one output stream."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.merge",
        version=1,
        display_name="Merge",
        description="Combine items from two inputs (append, zip by position, or join by key).",
        icon="icons/merge.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[
            Port(name=_INPUT_A, index=0, display_name="Input A"),
            Port(name=_INPUT_B, index=1, display_name="Input B"),
        ],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="mode",
                display_name="Mode",
                type="options",
                default=_MODE_APPEND,
                options=[PropertyOption(value=m, label=m) for m in _MODES],
            ),
            PropertySchema(
                name="key",
                display_name="Join key",
                type="string",
                default="",
                description="Dotted path evaluated on each item. Required for combine_by_key.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Combine ``input_a`` + ``input_b`` according to the configured mode."""
        del items  # Merge reads both ports directly; the executor's default
        # single-port `items` argument carries the main input, but we also
        # need input B, so we always pull from ``ctx`` explicitly.
        mode = str(ctx.param("mode", _MODE_APPEND))
        if mode not in _MODES:
            msg = f"Merge node received unknown mode {mode!r}"
            raise ValueError(msg)

        left = list(ctx.get_input(_INPUT_A))
        right = list(ctx.get_input(_INPUT_B))

        if mode == _MODE_APPEND:
            return [left + right]
        if mode == _MODE_BY_POSITION:
            return [_combine_by_position(left, right)]

        key = str(ctx.param("key", "")).strip()
        if not key:
            msg = "Merge node requires 'key' for combine_by_key mode"
            raise ValueError(msg)
        return [_combine_by_key(left, right, key=key)]


def _combine_by_position(left: list[Item], right: list[Item]) -> list[Item]:
    paired_count = min(len(left), len(right))
    out: list[Item] = []
    for i in range(paired_count):
        merged = {**left[i].json, **right[i].json}
        out.append(Item(json=merged))
    return out


def _combine_by_key(left: list[Item], right: list[Item], *, key: str) -> list[Item]:
    index: dict[Any, list[Item]] = {}
    for item in right:
        value = get_path(item.json, key)
        index.setdefault(_hashable(value), []).append(item)

    out: list[Item] = []
    for l_item in left:
        needle = _hashable(get_path(l_item.json, key))
        for r_item in index.get(needle, []):
            merged = {**l_item.json, **r_item.json}
            out.append(Item(json=merged))
    return out


def _hashable(value: Any) -> Any:
    # JSON-friendly values that might not be hashable (dict / list) are
    # serialised to a deterministic string so they still participate in the
    # join without raising TypeError.
    if isinstance(value, (dict, list)):
        import json  # noqa: PLC0415

        return json.dumps(value, sort_keys=True)
    return value
