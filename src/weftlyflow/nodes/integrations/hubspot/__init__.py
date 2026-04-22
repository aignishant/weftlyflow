"""HubSpot integration — CRM v3 contact CRUD and search.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.hubspot.node import HubSpotNode

NODE = HubSpotNode

__all__ = ["NODE", "HubSpotNode"]
