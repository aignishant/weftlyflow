"""Ghost Admin integration — posts, pages, members, tags via Admin API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.ghost.node import GhostNode

NODE = GhostNode

__all__ = ["NODE", "GhostNode"]
