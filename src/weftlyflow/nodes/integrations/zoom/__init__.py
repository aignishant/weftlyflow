"""Zoom integration — Meetings lifecycle over Server-to-Server Bearer.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.zoom.node import ZoomNode

NODE = ZoomNode

__all__ = ["NODE", "ZoomNode"]
