"""Discord integration — channel messages via the Discord REST API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.discord.node import DiscordNode

NODE = DiscordNode

__all__ = ["NODE", "DiscordNode"]
