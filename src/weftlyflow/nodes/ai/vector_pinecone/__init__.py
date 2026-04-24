"""Vector Pinecone node - managed vector store backed by Pinecone.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.vector_pinecone.node import VectorPineconeNode

NODE = VectorPineconeNode

__all__ = ["NODE", "VectorPineconeNode"]
