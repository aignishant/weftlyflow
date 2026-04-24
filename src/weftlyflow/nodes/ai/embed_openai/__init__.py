"""Embed OpenAI node - OpenAI ``/v1/embeddings`` batch embedder.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.embed_openai.node import EmbedOpenAINode

NODE = EmbedOpenAINode

__all__ = ["NODE", "EmbedOpenAINode"]
