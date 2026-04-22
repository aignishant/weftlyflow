"""Wait node — pause the current execution for a bounded duration.

Supports two modes:

* ``duration`` — sleep ``seconds`` before forwarding items. Handy for
  rate-limit back-off or synthetic delays in tests.
* ``until`` — sleep until the absolute ISO-8601 timestamp in
  ``until_datetime`` (interpreted in UTC if no tzinfo is present). If
  the timestamp is already in the past the node returns immediately.

The node cooperates with :attr:`ExecutionContext.canceled` by sleeping in
short slices — a canceled execution wakes up promptly instead of
blocking the worker for the full duration.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import ClassVar

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

_MODE_DURATION: str = "duration"
_MODE_UNTIL: str = "until"
_MODES: tuple[str, ...] = (_MODE_DURATION, _MODE_UNTIL)
_SLICE_SECONDS: float = 0.25
_MAX_SECONDS: float = 24 * 60 * 60


class WaitNode(BaseNode):
    """Sleep for a fixed duration or until an absolute time, then pass through."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.wait",
        version=1,
        display_name="Wait",
        description="Pause execution for a duration or until a given datetime.",
        icon="icons/wait.svg",
        category=NodeCategory.CORE,
        group=["logic"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="mode",
                display_name="Mode",
                type="options",
                default=_MODE_DURATION,
                options=[
                    PropertyOption(value=_MODE_DURATION, label="Duration"),
                    PropertyOption(value=_MODE_UNTIL, label="Until datetime"),
                ],
            ),
            PropertySchema(
                name="seconds",
                display_name="Seconds",
                type="number",
                default=1.0,
                description="Duration to wait when mode=duration.",
            ),
            PropertySchema(
                name="until_datetime",
                display_name="Until datetime (ISO-8601)",
                type="string",
                default="",
                description="Absolute time to wait until when mode=until.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Sleep according to the configured mode, then forward items unchanged."""
        mode = str(ctx.param("mode", _MODE_DURATION))
        if mode not in _MODES:
            msg = f"Wait: unknown mode {mode!r}"
            raise ValueError(msg)

        target_seconds = (
            _duration_seconds(ctx)
            if mode == _MODE_DURATION
            else _until_seconds(ctx)
        )
        await _sleep_cooperatively(target_seconds, ctx=ctx)
        return [list(items)]


def _duration_seconds(ctx: ExecutionContext) -> float:
    raw = ctx.resolved_param("seconds", 0)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Wait: 'seconds' must be a number, got {raw!r}"
        raise ValueError(msg) from exc
    if value < 0:
        msg = "Wait: 'seconds' must be non-negative"
        raise ValueError(msg)
    if value > _MAX_SECONDS:
        msg = f"Wait: 'seconds' exceeds the {_MAX_SECONDS:.0f}s cap"
        raise ValueError(msg)
    return value


def _until_seconds(ctx: ExecutionContext) -> float:
    raw = str(ctx.resolved_param("until_datetime", "") or "").strip()
    if not raw:
        msg = "Wait: 'until_datetime' is required for mode=until"
        raise ValueError(msg)
    try:
        target = datetime.fromisoformat(raw)
    except ValueError as exc:
        msg = f"Wait: 'until_datetime' is not ISO-8601: {raw!r}"
        raise ValueError(msg) from exc
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    delta = (target - datetime.now(tz=UTC)).total_seconds()
    return max(delta, 0.0)


async def _sleep_cooperatively(total: float, *, ctx: ExecutionContext) -> None:
    remaining = total
    while remaining > 0 and not ctx.canceled:
        slice_ = min(_SLICE_SECONDS, remaining)
        await asyncio.sleep(slice_)
        remaining -= slice_
