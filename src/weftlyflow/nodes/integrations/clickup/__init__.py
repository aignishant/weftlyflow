"""ClickUp integration — v2 REST API for task management.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.clickup.node import ClickUpNode

NODE = ClickUpNode

__all__ = ["NODE", "ClickUpNode"]
