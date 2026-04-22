"""Stripe integration — customers and payment intents.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.stripe.node import StripeNode

NODE = StripeNode

__all__ = ["NODE", "StripeNode"]
