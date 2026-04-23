"""Asana integration — tasks + stories over v1.0 REST.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.asana.node import AsanaNode

NODE = AsanaNode

__all__ = ["NODE", "AsanaNode"]
