"""Rocket.Chat integration — messaging, channels, users via REST v1.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.rocket_chat.node import RocketChatNode

NODE = RocketChatNode

__all__ = ["NODE", "RocketChatNode"]
