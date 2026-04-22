"""DateTime Ops node — parse / format / shift timestamps.

Writes the result into a named field on each item (``output_field``, default
``"at"``). The ``operation`` parameter selects what happens:

* ``now``          — current UTC (or ``timezone``) time.
* ``parse``        — parse ``source`` as ISO-8601 into the canonical form.
* ``format``       — reformat ``source`` (ISO-8601 in) using ``format`` pattern.
* ``add``          — take ``source``, add ``amount`` ``unit`` (e.g. days, hours).
* ``subtract``     — subtract ``amount`` ``unit``.
* ``diff_seconds`` — emit ``source_a - source_b`` in seconds.

Time sources are read via dotted paths in ``source``/``source_b``.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
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
from weftlyflow.nodes.utils import get_path, set_path

_OP_NOW: str = "now"
_OP_PARSE: str = "parse"
_OP_FORMAT: str = "format"
_OP_ADD: str = "add"
_OP_SUB: str = "subtract"
_OP_DIFF: str = "diff_seconds"
_OPERATIONS: tuple[str, ...] = (_OP_NOW, _OP_PARSE, _OP_FORMAT, _OP_ADD, _OP_SUB, _OP_DIFF)

_UNITS: dict[str, str] = {
    "seconds": "seconds",
    "minutes": "minutes",
    "hours": "hours",
    "days": "days",
    "weeks": "weeks",
}


class DateTimeOpsNode(BaseNode):
    """Do one datetime operation per input item and write the result to a field."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.datetime_ops",
        version=1,
        display_name="DateTime Ops",
        description="Parse, format, or shift ISO-8601 timestamps.",
        icon="icons/datetime.svg",
        category=NodeCategory.CORE,
        group=["transform"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=_OP_NOW,
                options=[PropertyOption(value=op, label=op) for op in _OPERATIONS],
            ),
            PropertySchema(
                name="source",
                display_name="Source field",
                type="string",
                default="",
                description="Dotted path to an ISO-8601 string on the input item.",
            ),
            PropertySchema(
                name="source_b",
                display_name="Second source (diff_seconds)",
                type="string",
                default="",
            ),
            PropertySchema(
                name="unit",
                display_name="Unit (add/subtract)",
                type="options",
                default="seconds",
                options=[PropertyOption(value=u, label=u) for u in _UNITS],
            ),
            PropertySchema(
                name="amount",
                display_name="Amount (add/subtract)",
                type="number",
                default=0,
            ),
            PropertySchema(
                name="format",
                display_name="Format (strftime)",
                type="string",
                default="%Y-%m-%dT%H:%M:%S%z",
            ),
            PropertySchema(
                name="timezone",
                display_name="Timezone (IANA)",
                type="string",
                default="UTC",
            ),
            PropertySchema(
                name="output_field",
                display_name="Output field",
                type="string",
                default="at",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Apply the selected operation per item and return the new stream."""
        operation = str(ctx.param("operation", _OP_NOW))
        if operation not in _OPERATIONS:
            msg = f"DateTime Ops: unknown operation {operation!r}"
            raise ValueError(msg)
        tz = _resolve_timezone(str(ctx.param("timezone", "UTC")))
        output_field = str(ctx.param("output_field", "at")) or "at"

        seed = items or [Item()]
        out: list[Item] = []
        for item in seed:
            value = _compute(operation, item, ctx, tz)
            payload: dict[str, Any] = copy.deepcopy(item.json)
            set_path(payload, output_field, value)
            out.append(Item(json=payload, binary=item.binary, paired_item=item.paired_item))
        return [out]


def _compute(
    operation: str,
    item: Item,
    ctx: ExecutionContext,
    tz: timezone,
) -> Any:
    if operation == _OP_NOW:
        return datetime.now(tz).isoformat()
    if operation == _OP_PARSE:
        source = _read_datetime(item, str(ctx.param("source", "")))
        return source.astimezone(tz).isoformat()
    if operation == _OP_FORMAT:
        source = _read_datetime(item, str(ctx.param("source", "")))
        fmt = str(ctx.param("format", "%Y-%m-%dT%H:%M:%S%z"))
        return source.astimezone(tz).strftime(fmt)
    if operation in {_OP_ADD, _OP_SUB}:
        source = _read_datetime(item, str(ctx.param("source", "")))
        unit = str(ctx.param("unit", "seconds"))
        if unit not in _UNITS:
            msg = f"DateTime Ops: unknown unit {unit!r}"
            raise ValueError(msg)
        amount = float(ctx.param("amount", 0) or 0)
        delta = timedelta(**{unit: amount})
        shifted = source + delta if operation == _OP_ADD else source - delta
        return shifted.astimezone(tz).isoformat()
    if operation == _OP_DIFF:
        a = _read_datetime(item, str(ctx.param("source", "")))
        b = _read_datetime(item, str(ctx.param("source_b", "")))
        return (a - b).total_seconds()
    msg = f"DateTime Ops: unreachable operation {operation!r}"
    raise AssertionError(msg)  # pragma: no cover


def _read_datetime(item: Item, path: str) -> datetime:
    if not path:
        msg = "DateTime Ops: source path is required for this operation"
        raise ValueError(msg)
    raw = get_path(item.json, path)
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if not isinstance(raw, str) or not raw:
        msg = f"DateTime Ops: field {path!r} is missing or not a string"
        raise ValueError(msg)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _resolve_timezone(name: str) -> timezone:
    normalized = name.strip() or "UTC"
    if normalized.upper() == "UTC":
        return UTC
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415 — stdlib lazy import.

        zone = ZoneInfo(normalized)
    except Exception as exc:
        msg = f"DateTime Ops: unknown timezone {name!r}"
        raise ValueError(msg) from exc
    # ZoneInfo is a tzinfo subclass but the typing helper we return is
    # the abstract base; callers only use it via astimezone().
    return zone  # type: ignore[return-value]


