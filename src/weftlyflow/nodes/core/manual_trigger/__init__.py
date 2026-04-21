"""Manual trigger — user-initiated workflow kick-off.

Exposes the node class as ``NODE`` so the discovery walker can register it.
"""

from __future__ import annotations

from weftlyflow.nodes.core.manual_trigger.node import ManualTriggerNode

NODE = ManualTriggerNode

__all__ = ["NODE", "ManualTriggerNode"]
