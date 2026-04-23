"""Anthropic integration — Messages, models, token-counting via the v1 API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.anthropic.node import AnthropicNode

NODE = AnthropicNode

__all__ = ["NODE", "AnthropicNode"]
