"""Twitch integration — Helix read-only endpoints via dual-header auth.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.twitch.node import TwitchNode

NODE = TwitchNode

__all__ = ["NODE", "TwitchNode"]
