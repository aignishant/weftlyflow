"""Text Splitter node - recursive chunker for RAG pipelines.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.text_splitter.node import TextSplitterNode

NODE = TextSplitterNode

__all__ = ["NODE", "TextSplitterNode"]
