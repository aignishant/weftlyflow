"""Linear integration — GraphQL API for issues, teams, projects.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.linear.node import LinearNode

NODE = LinearNode

__all__ = ["NODE", "LinearNode"]
