"""Binance Spot integration — account, tickers, orders.

Uses :class:`~weftlyflow.credentials.types.binance_api.BinanceApiCredential`.
Signed endpoints append a hex-encoded HMAC-SHA256 signature to the
query string; public endpoints (ticker price) skip signing entirely.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.binance.node import BinanceNode

NODE = BinanceNode

__all__ = ["NODE", "BinanceNode"]
