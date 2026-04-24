"""Chat-trigger node — start a workflow from an inbound chat message.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.trigger_chat.node import ChatTriggerNode

NODE = ChatTriggerNode

__all__ = ["NODE", "ChatTriggerNode"]
