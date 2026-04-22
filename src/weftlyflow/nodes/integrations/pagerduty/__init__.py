"""PagerDuty integration — REST v2 API for incident management.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.pagerduty.node import PagerDutyNode

NODE = PagerDutyNode

__all__ = ["NODE", "PagerDutyNode"]
