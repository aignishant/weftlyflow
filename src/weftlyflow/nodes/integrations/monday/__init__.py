"""Monday.com integration — GraphQL v2 API for boards, items, and updates.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.monday.node import MondayNode

NODE = MondayNode

__all__ = ["NODE", "MondayNode"]
