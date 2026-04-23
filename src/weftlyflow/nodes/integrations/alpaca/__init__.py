"""Alpaca Markets integration — account, positions, orders, clock.

Uses :class:`~weftlyflow.credentials.types.alpaca_api.AlpacaApiCredential`.
The base host is selected from the credential's ``environment`` field
(paper vs live); auth travels in the two ``APCA-API-*`` headers.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.alpaca.node import AlpacaNode

NODE = AlpacaNode

__all__ = ["NODE", "AlpacaNode"]
