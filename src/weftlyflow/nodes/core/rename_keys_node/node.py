"""Rename Keys node — apply a list of key-to-key renames on each item.

Supports dotted paths on both sides (``"user.firstName" → "user.first_name"``)
so simple nested renames don't need a Code node. ``drop_missing`` controls
whether renaming a missing source key is an error or a silent pass.
"""

from __future__ import annotations

from typing import Any, ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.utils import del_path, get_path, set_path


class RenameKeysNode(BaseNode):
    """Rename keys in each item's JSON payload."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.rename_keys",
        version=1,
        display_name="Rename Keys",
        description="Rename keys in each item's JSON payload using dotted paths.",
        icon="icons/rename-keys.svg",
        category=NodeCategory.CORE,
        group=["transform"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="mappings",
                display_name="Mappings",
                type="json",
                default=[],
                description=(
                    'List of `{"from": "user.firstName", "to": "user.first_name"}`. '
                    "Paths are dotted, same as the If/Set nodes."
                ),
            ),
            PropertySchema(
                name="drop_missing",
                display_name="Skip missing source keys",
                type="boolean",
                default=True,
                description=(
                    "When True, renaming a missing key is a no-op. "
                    "When False, the node raises on missing source keys."
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Apply every mapping to each item and emit the rewritten stream."""
        mappings = _coerce_mappings(ctx.param("mappings", []))
        drop_missing = bool(ctx.param("drop_missing", True))
        if not mappings:
            return [list(items)]

        out: list[Item] = []
        for item in items:
            payload: dict[str, Any] = _deep_copy_json(item.json)
            for entry in mappings:
                source = entry["from"]
                target = entry["to"]
                if source == target:
                    continue
                value = get_path(payload, source, default=_MISSING)
                if value is _MISSING:
                    if not drop_missing:
                        msg = f"Rename Keys: missing source key {source!r}"
                        raise KeyError(msg)
                    continue
                del_path(payload, source)
                set_path(payload, target, value)
            out.append(
                Item(
                    json=payload,
                    binary=item.binary,
                    paired_item=item.paired_item,
                    error=item.error,
                ),
            )
        return [out]


_MISSING: Any = object()


def _deep_copy_json(value: Any) -> Any:
    # set_path / del_path mutate in place, so we need a full copy before
    # writing. Items are JSON-shaped so a manual walk is enough.
    if isinstance(value, dict):
        return {key: _deep_copy_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_deep_copy_json(item) for item in value]
    return value


def _coerce_mappings(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        src = entry.get("from")
        dst = entry.get("to")
        if isinstance(src, str) and isinstance(dst, str) and src and dst:
            out.append({"from": src, "to": dst})
    return out
