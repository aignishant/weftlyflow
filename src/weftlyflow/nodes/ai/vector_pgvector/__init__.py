"""Vector Pgvector node - persistent vector store backed by pgvector.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.vector_pgvector.node import VectorPgvectorNode

NODE = VectorPgvectorNode

__all__ = ["NODE", "VectorPgvectorNode"]
