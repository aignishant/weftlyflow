"""Telegram integration — Bot API for messaging.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.telegram.node import TelegramNode

NODE = TelegramNode

__all__ = ["NODE", "TelegramNode"]
