"""Filter node — drop items that fail a predicate.

Two ways to express the predicate:

* the same ``field``/``operator``/``value`` triple that :class:`IfNode`
  exposes, which keeps the UX consistent with the binary-branch node;
* an ``expression`` parameter, evaluated per-item via the expression
  engine. When both are set, the expression wins.

Items that raise during predicate evaluation are dropped unless
``keep_on_error`` is True — the same policy n8n-style users expect from a
"filter" node.
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
from weftlyflow.expression.errors import ExpressionError
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


class FilterNode(BaseNode):
    """Keep only the items for which the predicate is truthy."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.filter",
        version=1,
        display_name="Filter",
        description="Drop items that fail the configured predicate.",
        icon="icons/filter.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="expression",
                display_name="Expression",
                type="expression",
                default="",
                description=(
                    "Optional {{ ... }} template. When set, overrides the "
                    "field/operator/value triple."
                ),
            ),
            PropertySchema(
                name="field",
                display_name="Field",
                type="string",
                default="",
                placeholder="status",
            ),
            PropertySchema(
                name="operator",
                display_name="Operator",
                type="options",
                default="equals",
                options=_OPERATOR_OPTIONS,
            ),
            PropertySchema(
                name="value",
                display_name="Value",
                type="string",
                default=None,
            ),
            PropertySchema(
                name="keep_on_error",
                display_name="Keep items on evaluation error",
                type="boolean",
                default=False,
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Return the items where the predicate evaluates truthy."""
        expression = str(ctx.param("expression", "")).strip()
        field = str(ctx.param("field", "")).strip()
        operator: PredicateOperator = ctx.param("operator", "equals")
        right: Any = ctx.param("value", None)
        keep_on_error = bool(ctx.param("keep_on_error", False))

        if not expression and not field:
            msg = "Filter node requires either 'expression' or 'field' to be set"
            raise ValueError(msg)
        if not expression and operator not in PREDICATE_OPERATORS:
            msg = f"Filter node received unknown operator: {operator!r}"
            raise ValueError(msg)

        kept: list[Item] = []
        for item in items:
            try:
                if expression:
                    result = ctx.resolved_param("expression", item=item)
                    if bool(result):
                        kept.append(item)
                else:
                    left = get_path(item.json, field)
                    if evaluate_predicate(left, operator, right):
                        kept.append(item)
            except ExpressionError:
                if keep_on_error:
                    kept.append(item)
        return [kept]
