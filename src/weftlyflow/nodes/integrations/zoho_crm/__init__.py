"""Zoho CRM integration — v6 REST API for modules and records.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.zoho_crm.node import ZohoCrmNode

NODE = ZohoCrmNode

__all__ = ["NODE", "ZohoCrmNode"]
