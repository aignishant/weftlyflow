"""Backblaze B2 integration — bucket + file ops against the Native API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.backblaze_b2.node import BackblazeB2Node

NODE = BackblazeB2Node

__all__ = ["NODE", "BackblazeB2Node"]
