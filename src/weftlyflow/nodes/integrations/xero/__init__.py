"""Xero integration — invoices, contacts, accounts via the Accounting API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.xero.node import XeroNode

NODE = XeroNode

__all__ = ["NODE", "XeroNode"]
