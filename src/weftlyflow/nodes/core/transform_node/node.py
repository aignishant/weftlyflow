"""Transform node — expression-driven per-item remap.

Where :class:`~weftlyflow.nodes.core.set_node.node.SetNode` writes literal
values, ``transform`` re-evaluates each assignment's ``value`` through the
expression engine for every input item. This makes it the go-to node for
computing new fields from existing ones without a Code node.

Parameters:

* ``assignments`` — list of ``{"name": dotted.path, "value": any}``. The
  ``value`` may contain ``{{ ... }}`` placeholders and is resolved per item.
* ``mode`` — ``"merge"`` (default) keeps the original fields and overlays
  the computed ones; ``"replace"`` starts from an empty object and emits
  only the computed fields (useful for projecting).

Errors encountered while resolving an assignment are raised as
:class:`ValueError` to surface bad templates loudly; per-item swallowing is
deliberately left to :class:`FilterNode`-style predicates rather than
baked in here.
"""

from __future__ import annotations

from copy import deepcopy
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
from weftlyflow.nodes.utils import set_path

_MODE_MERGE: str = "merge"
_MODE_REPLACE: str = "replace"
_MODES: tuple[str, ...] = (_MODE_MERGE, _MODE_REPLACE)


class TransformNode(BaseNode):
    """Re-map each item's JSON using per-item expression assignments."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.transform",
        version=1,
        display_name="Transform",
        description="Compute new fields per item using {{ expressions }}.",
        icon="icons/transform.svg",
        category=NodeCategory.CORE,
        group=["transform"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="assignments",
                display_name="Assignments",
                type="fixed_collection",
                default=[],
                description=(
                    'List of `{"name": "user.upper", "value": "{{ $json.name.upper() }}"}`. '
                    "Expressions are re-evaluated per item."
                ),
            ),
            PropertySchema(
                name="mode",
                display_name="Mode",
                type="options",
                default=_MODE_MERGE,
                options=[PropertyOption(value=m, label=m.title()) for m in _MODES],
                description=(
                    "'merge' keeps existing fields, 'replace' emits only the "
                    "computed fields."
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Resolve every assignment per input item and emit the rewritten stream."""
        raw_assignments = ctx.param("assignments", [])
        mode = str(ctx.param("mode", _MODE_MERGE))
        if mode not in _MODES:
            msg = f"Transform: unknown mode {mode!r}"
            raise ValueError(msg)
        assignments = _coerce_assignments(raw_assignments)
        if not assignments:
            return [list(items)]

        out: list[Item] = [
            _transform_one(item, ctx=ctx, assignments=assignments, mode=mode)
            for item in items
        ]
        return [out]


def _transform_one(
    item: Item,
    *,
    ctx: ExecutionContext,
    assignments: list[tuple[str, Any]],
    mode: str,
) -> Item:
    base: dict[str, Any] = {} if mode == _MODE_REPLACE else deepcopy(item.json)
    # ``resolved_params`` walks the whole parameter dict once per item, so the
    # assignment values are re-resolved with the current item as ``$json``.
    resolved = ctx.resolved_params(item=item)
    resolved_entries = resolved.get("assignments")
    if not isinstance(resolved_entries, list):
        resolved_entries = []
    for (name, _), resolved_entry in zip(assignments, resolved_entries, strict=False):
        if not isinstance(resolved_entry, dict):
            continue
        set_path(base, name, resolved_entry.get("value"))
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
