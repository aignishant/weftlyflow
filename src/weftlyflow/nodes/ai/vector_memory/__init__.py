"""Vector Memory node - in-process vector store for RAG workflows.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.vector_memory.node import VectorMemoryNode

NODE = VectorMemoryNode

__all__ = ["NODE", "VectorMemoryNode"]
