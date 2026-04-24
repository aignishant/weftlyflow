"""Memory Buffer node — session-keyed chat history persistence.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.memory_buffer.node import MemoryBufferNode

NODE = MemoryBufferNode

__all__ = ["NODE", "MemoryBufferNode"]
