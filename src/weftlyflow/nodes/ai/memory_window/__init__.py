"""Memory Window node — sliding-window chat history.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.memory_window.node import MemoryWindowNode

NODE = MemoryWindowNode

__all__ = ["NODE", "MemoryWindowNode"]
