"""Airtable integration — records CRUD via the v0 REST API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.airtable.node import AirtableNode

NODE = AirtableNode

__all__ = ["NODE", "AirtableNode"]
