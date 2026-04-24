"""Vector Qdrant node - external vector store backed by Qdrant.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.vector_qdrant.node import VectorQdrantNode

NODE = VectorQdrantNode

__all__ = ["NODE", "VectorQdrantNode"]
