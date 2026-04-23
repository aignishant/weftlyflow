"""OpenAI integration — chat completions, embeddings, moderation, images.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.openai.node import OpenAINode

NODE = OpenAINode

__all__ = ["NODE", "OpenAINode"]
