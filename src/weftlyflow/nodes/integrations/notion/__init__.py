"""Notion integration — pages and database queries.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.notion.node import NotionNode

NODE = NotionNode

__all__ = ["NODE", "NotionNode"]
