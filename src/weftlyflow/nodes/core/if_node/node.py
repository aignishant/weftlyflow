"""If node — boolean branching with two output ports.

Node parameters (all consumed via ``ctx.param``):

- ``field``: Dotted path read from ``item.json`` (e.g. ``"user.age"``).
- ``operator``: One of :data:`weftlyflow.nodes.utils.predicates.PREDICATE_OPERATORS`.
- ``value``: Right-hand side literal for binary operators. Ignored for unary ones.
- ``combine_mode``: ``"any"`` / ``"all"`` — how to combine multiple conditions.
  Phase 1 exposes only a single-condition form; the parameter is kept so
  Phase 4's expression-driven multi-condition variant slots in without a
  schema change.

Output ports:

- ``true``: items for which the predicate evaluates True.
- ``false``: items for which the predicate evaluates False.
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
from weftlyflow.nodes.utils import (
    PREDICATE_OPERATORS,
    PredicateOperator,
    evaluate_predicate,
    get_path,
)

_OPERATOR_OPTIONS: list[PropertyOption] = [
    PropertyOption(value=op, label=op.replace("_", " ").title())
    for op in PREDICATE_OPERATORS
]


class IfNode(BaseNode):
    """Split the input stream into ``true`` and ``false`` output ports."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.if",
        version=1,
        display_name="If",
        description="Route items to true/false based on a predicate.",
        icon="icons/if.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[Port(name="main")],
        outputs=[Port(name="true"), Port(name="false")],
        properties=[
            PropertySchema(
                name="field",
                display_name="Field",
                type="string",
                required=True,
                placeholder="user.age",
                description="Dotted path evaluated against each item's JSON payload.",
            ),
            PropertySchema(
                name="operator",
                display_name="Operator",
                type="options",
                required=True,
                default="equals",
                options=_OPERATOR_OPTIONS,
            ),
            PropertySchema(
                name="value",
                display_name="Value",
                type="string",
                default=None,
                description="Right-hand side for binary operators.",
            ),
            PropertySchema(
                name="combine_mode",
                display_name="Combine conditions",
                type="options",
                default="all",
                options=[
                    PropertyOption(value="all", label="All (AND)"),
                    PropertyOption(value="any", label="Any (OR)"),
                ],
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Partition ``items`` by the configured predicate into two output ports."""
        field = str(ctx.param("field", default=""))
        operator: PredicateOperator = ctx.param("operator", default="equals")
        right: Any = ctx.param("value", default=None)

        if not field:
            msg = "If node requires a non-empty 'field' parameter"
            raise ValueError(msg)
        if operator not in PREDICATE_OPERATORS:
            msg = f"If node received unknown operator: {operator!r}"
            raise ValueError(msg)

        true_items: list[Item] = []
        false_items: list[Item] = []
        for item in items:
            left = get_path(item.json, field)
            bucket = true_items if evaluate_predicate(left, operator, right) else false_items
            bucket.append(item)

        return [true_items, false_items]
