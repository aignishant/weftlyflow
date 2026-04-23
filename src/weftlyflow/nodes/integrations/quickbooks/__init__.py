"""QuickBooks Online integration — query + invoice/customer CRUD via v3 API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.quickbooks.node import QuickBooksNode

NODE = QuickBooksNode

__all__ = ["NODE", "QuickBooksNode"]
