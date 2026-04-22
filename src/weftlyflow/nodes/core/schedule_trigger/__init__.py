"""Schedule-trigger node — start a workflow on a cron or interval schedule."""

from __future__ import annotations

from weftlyflow.nodes.core.schedule_trigger.node import ScheduleTriggerNode

NODE = ScheduleTriggerNode

__all__ = ["NODE", "ScheduleTriggerNode"]
