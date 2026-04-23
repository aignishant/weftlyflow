"""Coinbase Exchange integration — accounts, tickers, orders.

Uses :class:`~weftlyflow.credentials.types.coinbase_exchange.CoinbaseExchangeCredential`.
Every request is HMAC-SHA256 signed over ``timestamp + method + path +
body`` and carries four ``CB-ACCESS-*`` headers. The credential reads
the final request path and body off the :class:`httpx.Request` so the
node can stay declarative.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.coinbase.node import CoinbaseNode

NODE = CoinbaseNode

__all__ = ["NODE", "CoinbaseNode"]
