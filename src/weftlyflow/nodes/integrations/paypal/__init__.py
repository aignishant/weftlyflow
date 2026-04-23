"""PayPal REST integration — orders, payments, refunds via the v2 API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.paypal.node import PayPalNode

NODE = PayPalNode

__all__ = ["NODE", "PayPalNode"]
