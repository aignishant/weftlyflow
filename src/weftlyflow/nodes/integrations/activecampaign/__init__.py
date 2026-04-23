"""ActiveCampaign integration — CRM contacts, lists, and tags.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.activecampaign.node import ActiveCampaignNode

NODE = ActiveCampaignNode

__all__ = ["NODE", "ActiveCampaignNode"]
