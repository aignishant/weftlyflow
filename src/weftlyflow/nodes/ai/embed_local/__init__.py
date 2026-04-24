"""Embed Local node - deterministic hashing embeddings with no API.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.embed_local.node import EmbedLocalNode

NODE = EmbedLocalNode

__all__ = ["NODE", "EmbedLocalNode"]
