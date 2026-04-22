"""Switch node — multi-way branch by field value.

The If node is binary. Switch is the N-way equivalent: each case declares a
``port`` name + a literal value to match against the item's field, and
unmatched items land on the ``default`` port.

Output ports are **declared dynamically** from the ``cases`` parameter plus
a terminal ``default``. Because :class:`NodeSpec` is frozen and shared
across all instances, the outputs listed there are the *schema* (what the
editor shows); the engine routes by the port names the node writes back on
``execute``. We expose the fixed ports ``default`` + ``case_1..case_N`` and
match the string labels declared in parameters — this matches how users
wire the editor today without needing dynamic port generation in Phase 6.

Parameters:

* ``field``: dotted path read from ``item.json``.
* ``cases``: ``list[{"value": Any, "port": str}]``. ``port`` must be one of
  the spec's output ports.
* ``fallback_port``: name of the port for items that matched no case.
"""

from __future__ import annotations

from typing import Any, ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.utils import get_path

_MAX_PORTS: int = 6
_DEFAULT_PORT: str = "default"


class SwitchNode(BaseNode):
    """Route each item to the output port whose case matches its field value."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.switch",
        version=1,
        display_name="Switch",
        description="Route items to one of several output ports based on a field value.",
        icon="icons/switch.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[Port(name="main")],
        outputs=[
            *(Port(name=f"case_{i}", index=i) for i in range(1, _MAX_PORTS + 1)),
            Port(name=_DEFAULT_PORT, index=_MAX_PORTS),
        ],
        properties=[
            PropertySchema(
                name="field",
                display_name="Field",
                type="string",
                required=True,
                placeholder="status",
            ),
            PropertySchema(
                name="cases",
                display_name="Cases",
                type="json",
                default=[],
                description=(
                    'List of `{"value": ..., "port": "case_1"}`. '
                    'Items matching the first case flow through its port.'
                ),
            ),
            PropertySchema(
                name="fallback_port",
                display_name="Fallback port",
                type="string",
                default=_DEFAULT_PORT,
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Bucket ``items`` by case and emit one list per output port."""
        field = str(ctx.param("field", "")).strip()
        if not field:
            msg = "Switch node requires a non-empty 'field' parameter"
            raise ValueError(msg)

        cases_raw: Any = ctx.param("cases", [])
        cases = _coerce_cases(cases_raw)
        fallback = str(ctx.param("fallback_port", _DEFAULT_PORT))

        known_ports = [port.name for port in self.spec.outputs]
        if fallback not in known_ports:
            msg = f"Switch fallback_port {fallback!r} is not a declared output"
            raise ValueError(msg)

        buckets: dict[str, list[Item]] = {name: [] for name in known_ports}

        for item in items:
            left = get_path(item.json, field)
            target = fallback
            for case in cases:
                if case["port"] not in buckets:
                    msg = f"Switch case references unknown port {case['port']!r}"
                    raise ValueError(msg)
                if _values_match(left, case["value"]):
                    target = case["port"]
                    break
            buckets[target].append(item)

        return [buckets[name] for name in known_ports]


def _coerce_cases(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        port = entry.get("port")
        if not isinstance(port, str):
            continue
        out.append({"value": entry.get("value"), "port": port})
    return out


def _values_match(left: Any, right: Any) -> bool:
    # Equal-by-value with a string-ish fallback so users writing case values
    # in a JSON textarea can match numeric fields with the string form too.
    if left == right:
        return True
    return isinstance(left, str) != isinstance(right, str) and str(left) == str(right)
