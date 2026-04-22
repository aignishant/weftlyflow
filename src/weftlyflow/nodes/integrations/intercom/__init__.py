"""Intercom integration — v2.x REST API for contacts and conversations.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.intercom.node import IntercomNode

NODE = IntercomNode

__all__ = ["NODE", "IntercomNode"]
