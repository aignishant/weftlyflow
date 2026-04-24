"""Mistral La Plateforme integration — chat, FIM, embeddings via the v1 API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.mistral.node import MistralNode

NODE = MistralNode

__all__ = ["NODE", "MistralNode"]
