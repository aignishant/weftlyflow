"""Shopify integration — Admin REST API for products and orders.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.shopify.node import ShopifyNode

NODE = ShopifyNode

__all__ = ["NODE", "ShopifyNode"]
