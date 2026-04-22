"""Compare Datasets node — bucket items from two inputs by a shared key.

Takes two input streams (``main`` and ``input_2``) joined on a dotted
``key`` path and routes the items to four output ports:

* ``in_a_only`` — items whose key exists on the left only.
* ``in_b_only`` — items whose key exists on the right only.
* ``both_same`` — the left item when both sides exist AND their JSON
  payloads are equal.
* ``both_different`` — the left item paired with its right counterpart
  when both sides exist but the JSON payloads differ. The paired item is
  emitted as ``{"a": a.json, "b": b.json}`` so downstream nodes can
  inspect the delta without an extra join.

Keys that resolve to unhashable values (dicts / lists) are serialised to
a deterministic JSON string — matching the policy used by the Merge node
for consistency across joins.
"""

from __future__ import annotations

from typing import Any, ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.utils import get_path

_INPUT_A: str = "main"
_INPUT_B: str = "input_2"
_PORT_A_ONLY: str = "in_a_only"
_PORT_B_ONLY: str = "in_b_only"
_PORT_SAME: str = "both_same"
_PORT_DIFF: str = "both_different"


class CompareDatasetsNode(BaseNode):
    """Diff two input streams by key and route items to four output ports."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.compare_datasets",
        version=1,
        display_name="Compare Datasets",
        description="Diff two input streams by key into A-only / B-only / same / different.",
        icon="icons/compare-datasets.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[
            Port(name=_INPUT_A, index=0, display_name="Input A"),
            Port(name=_INPUT_B, index=1, display_name="Input B"),
        ],
        outputs=[
            Port(name=_PORT_A_ONLY, index=0, display_name="In A only"),
            Port(name=_PORT_B_ONLY, index=1, display_name="In B only"),
            Port(name=_PORT_SAME, index=2, display_name="Both (same)"),
            Port(name=_PORT_DIFF, index=3, display_name="Both (different)"),
        ],
        properties=[
            PropertySchema(
                name="key",
                display_name="Join key",
                type="string",
                default="id",
                required=True,
                description="Dotted path used to match items across inputs.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Route items into four buckets based on key membership and equality."""
        del items  # We pull both inputs explicitly.
        key = str(ctx.param("key", "")).strip()
        if not key:
            msg = "Compare Datasets: 'key' is required"
            raise ValueError(msg)

        left = list(ctx.get_input(_INPUT_A))
        right = list(ctx.get_input(_INPUT_B))

        left_index: dict[Any, Item] = {
            _hashable(get_path(item.json, key)): item for item in left
        }
        right_index: dict[Any, Item] = {
            _hashable(get_path(item.json, key)): item for item in right
        }

        a_only: list[Item] = []
        same: list[Item] = []
        diff: list[Item] = []
        for needle, l_item in left_index.items():
            r_item = right_index.get(needle)
            if r_item is None:
                a_only.append(l_item)
                continue
            if l_item.json == r_item.json:
                same.append(l_item)
            else:
                diff.append(Item(json={"a": l_item.json, "b": r_item.json}))

        b_only = [
            r_item
            for needle, r_item in right_index.items()
            if needle not in left_index
        ]
        return [a_only, b_only, same, diff]


def _hashable(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        import json  # noqa: PLC0415

        return json.dumps(value, sort_keys=True)
    return value
