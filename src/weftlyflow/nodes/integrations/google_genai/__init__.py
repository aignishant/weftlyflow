"""Google GenAI integration — Gemini generateContent + token counting.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.google_genai.node import GoogleGenAINode

NODE = GoogleGenAINode

__all__ = ["NODE", "GoogleGenAINode"]
