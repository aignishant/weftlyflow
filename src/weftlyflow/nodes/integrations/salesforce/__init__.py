"""Salesforce integration — sobjects REST + SOQL over per-org instance URL.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.salesforce.node import SalesforceNode

NODE = SalesforceNode

__all__ = ["NODE", "SalesforceNode"]
