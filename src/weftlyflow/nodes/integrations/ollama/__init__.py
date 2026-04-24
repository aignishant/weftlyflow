"""Ollama integration — local-LLM chat, completion, embeddings, model listing.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.ollama.node import OllamaNode

NODE = OllamaNode

__all__ = ["NODE", "OllamaNode"]
