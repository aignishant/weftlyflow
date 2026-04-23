"""Pinecone integration — indexes and vector operations.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.pinecone.node import PineconeNode

NODE = PineconeNode

__all__ = ["NODE", "PineconeNode"]
