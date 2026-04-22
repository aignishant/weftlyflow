"""Evaluate Expression node — run one expression per item, write to a field.

Think of it as the Set node's single-field cousin: rather than a list of
assignments, it takes one expression, evaluates it against each item's
context, and stores the result under ``output_field`` (default ``result``).
Useful as a scratch-pad inside workflows that chain several transforms.
"""

from __future__ import annotations

import copy
from typing import Any, ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.utils import set_path


class EvaluateExpressionNode(BaseNode):
    """Evaluate an expression per item and write the result to a field."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.evaluate_expression",
        version=1,
        display_name="Evaluate Expression",
        description="Evaluate a {{ ... }} expression against each item and store the result.",
        icon="icons/evaluate.svg",
        category=NodeCategory.CORE,
        group=["transform"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="expression",
                display_name="Expression",
                type="expression",
                required=True,
                placeholder="{{ $json.price * 1.2 }}",
            ),
            PropertySchema(
                name="output_field",
                display_name="Output field",
                type="string",
                default="result",
                description="Dotted path written into each item. Defaults to 'result'.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Evaluate the template once per item and emit the augmented stream."""
        template = str(ctx.param("expression", ""))
        if not template.strip():
            msg = "Evaluate Expression: 'expression' is required"
            raise ValueError(msg)
        output_field = str(ctx.param("output_field", "result")) or "result"

        seed = items or [Item()]
        out: list[Item] = []
        for item in seed:
            value: Any = ctx.resolved_param("expression", item=item)
            payload: dict[str, Any] = copy.deepcopy(item.json)
            set_path(payload, output_field, value)
            out.append(Item(json=payload, binary=item.binary, paired_item=item.paired_item))
        return [out]
