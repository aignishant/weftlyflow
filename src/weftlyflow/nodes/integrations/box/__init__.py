"""Box integration — Content API v2.0 folder/file + enterprise users.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.box.node import BoxNode

NODE = BoxNode

__all__ = ["NODE", "BoxNode"]
