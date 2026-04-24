"""Memory Summary node — rolling-summary chat history persistence.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.memory_summary.node import MemorySummaryNode

NODE = MemorySummaryNode

__all__ = ["NODE", "MemorySummaryNode"]
