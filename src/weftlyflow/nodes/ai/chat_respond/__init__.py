"""Chat Respond node - standardised chat-response envelope.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.chat_respond.node import ChatRespondNode

NODE = ChatRespondNode

__all__ = ["NODE", "ChatRespondNode"]
