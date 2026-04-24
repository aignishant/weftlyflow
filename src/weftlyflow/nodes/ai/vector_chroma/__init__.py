"""Vector Chroma node - self-hosted vector store via Chroma REST.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.vector_chroma.node import VectorChromaNode

NODE = VectorChromaNode

__all__ = ["NODE", "VectorChromaNode"]
