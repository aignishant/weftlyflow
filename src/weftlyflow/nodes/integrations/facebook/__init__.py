"""Facebook Graph integration — generic node/edge dispatcher.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.facebook.node import FacebookGraphNode

NODE = FacebookGraphNode

__all__ = ["NODE", "FacebookGraphNode"]
