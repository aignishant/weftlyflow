"""Schedule-trigger node — emits one empty item per scheduled tick.

Registration of the cron / interval is handled by the
:class:`weftlyflow.triggers.manager.ActiveTriggerManager` when the workflow
is activated. At execution time the node is a thin action node: it passes
through whatever the scheduler seeded (typically an empty ``Item``) and
annotates it with the trigger timestamp so downstream logic can identify
the run as scheduler-initiated.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from weftlyflow.triggers.constants import (
    SCHEDULE_KIND_INTERVAL,
    SCHEDULE_KINDS,
)


class ScheduleTriggerNode(BaseNode):
    """Start a workflow on a recurring schedule; emits one ``Item`` per tick."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.schedule_trigger",
        version=1,
        display_name="Schedule Trigger",
        description="Start the workflow on a cron expression or fixed interval.",
        icon="icons/schedule-trigger.svg",
        category=NodeCategory.TRIGGER,
        group=["trigger"],
        inputs=[],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="kind",
                display_name="Schedule kind",
                type="options",
                default=SCHEDULE_KIND_INTERVAL,
                required=True,
                options=[PropertyOption(value=k, label=k) for k in SCHEDULE_KINDS],
            ),
            PropertySchema(
                name="cron_expression",
                display_name="Cron expression",
                type="string",
                default="",
                description="Standard 5-field cron. Required when kind == cron.",
            ),
            PropertySchema(
                name="interval_seconds",
                display_name="Interval (seconds)",
                type="number",
                default=60,
                description="Run every N seconds. Required when kind == interval.",
            ),
            PropertySchema(
                name="timezone",
                display_name="Timezone",
                type="string",
                default="UTC",
                description="IANA tz name. Defaults to UTC.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Emit one annotated tick item; preserve any seeded payload under ``trigger``."""
        del ctx
        tick: dict[str, Any] = {"fired_at": datetime.now(UTC).isoformat()}
        if items:
            tick["seed"] = [dict(item.json) for item in items]
        return [[Item(json=tick)]]
