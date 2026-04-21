"""Set node — mutate the ``json`` payload of each incoming item.

Node parameters (all optional, all consumed via ``ctx.param``):

- ``assignments``: list of ``{"name": str, "value": Any}`` entries. Each
  writes ``value`` at the dotted ``name`` path on every item. Values are
  taken literally in Phase 1; Phase 4 will pre-evaluate them through the
  expression engine.
- ``removals``: dotted paths to delete from every item.
- ``keep_only_set``: when True, start from an empty dict and only emit the
  fields named in ``assignments`` (projection + PII stripping use case).

Items are copied so upstream nodes' outputs are not mutated in place.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertySchema,
)
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.utils import del_path, set_path


class SetNode(BaseNode):
    """Write, remove, or project fields on each item's JSON payload."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.set",
        version=1,
        display_name="Set",
        description="Add, overwrite, or remove fields on items.",
        icon="icons/set.svg",
        category=NodeCategory.CORE,
        group=["transform"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="assignments",
                display_name="Fields to set",
                type="fixed_collection",
                default=[],
                description="Each entry: {name: <dotted path>, value: <any>}.",
            ),
            PropertySchema(
                name="removals",
                display_name="Fields to remove",
                type="multi_options",
                default=[],
                description="List of dotted paths to delete from every item.",
            ),
            PropertySchema(
                name="keep_only_set",
                display_name="Keep only fields set here",
                type="boolean",
                default=False,
                description="Start from {} instead of copying the item's json.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Apply the configured mutations to each item and emit the result."""
        assignments = _coerce_assignments(ctx.param("assignments", []))
        removals = _coerce_removals(ctx.param("removals", []))
        keep_only = bool(ctx.param("keep_only_set", default=False))

        output: list[Item] = [
            _apply(item, assignments=assignments, removals=removals, keep_only=keep_only)
            for item in items
        ]
        return [output]


def _apply(
    item: Item,
    *,
    assignments: list[tuple[str, Any]],
    removals: list[str],
    keep_only: bool,
) -> Item:
    base: dict[str, Any] = {} if keep_only else deepcopy(item.json)
    for name, value in assignments:
        set_path(base, name, value)
    for path in removals:
        del_path(base, path)
    return Item(
        json=base,
        binary=dict(item.binary),
        paired_item=list(item.paired_item),
        error=item.error,
    )


def _coerce_assignments(raw: Any) -> list[tuple[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[tuple[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        result.append((name, entry.get("value")))
    return result


def _coerce_removals(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [path for path in raw if isinstance(path, str) and path]
