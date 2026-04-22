"""Pushover integration — push notifications via form-body auth.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.pushover.node import PushoverNode

NODE = PushoverNode

__all__ = ["NODE", "PushoverNode"]
