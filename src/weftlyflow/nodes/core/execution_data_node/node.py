"""Execution Data node — emit run-level metadata as an item.

The node merges ``{execution_id, workflow_id, project_id, mode}`` into
each item it sees (or emits one fresh item if the input stream is empty).
Useful as a source of correlation ids for downstream HTTP Request nodes
that need to stamp outbound webhooks / logs with the run they belong to.
"""

from __future__ import annotations

import copy
from typing import Any, ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode


class ExecutionDataNode(BaseNode):
    """Attach execution metadata to every item passing through."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.execution_data",
        version=1,
        display_name="Execution Data",
        description="Merge execution id / workflow id / mode into each item.",
        icon="icons/info.svg",
        category=NodeCategory.CORE,
        group=["utility"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="prefix",
                display_name="Field prefix",
                type="string",
                default="_execution",
                description=(
                    "Name of the subkey that holds the metadata. Set to an "
                    "empty string to merge at the top level."
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Merge execution metadata into every item and emit."""
        prefix = str(ctx.param("prefix", "_execution")).strip()
        meta: dict[str, Any] = {
            "execution_id": ctx.execution_id,
            "workflow_id": ctx.workflow.id,
            "project_id": ctx.workflow.project_id,
            "mode": ctx.mode,
        }
        seed = items or [Item()]
        out: list[Item] = []
        for item in seed:
            payload: dict[str, Any] = copy.deepcopy(item.json)
            if prefix:
                payload[prefix] = meta
            else:
                for key, value in meta.items():
                    payload.setdefault(key, value)
            out.append(Item(json=payload, binary=item.binary, paired_item=item.paired_item))
        return [out]
