"""Square integration — customers, payments, orders via the v2 REST API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.square.node import SquareNode

NODE = SquareNode

__all__ = ["NODE", "SquareNode"]
