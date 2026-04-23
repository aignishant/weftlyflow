"""Mixpanel integration — track, engage, groups, import via the HTTP API.

Uses :class:`~weftlyflow.credentials.types.mixpanel_api.MixpanelApiCredential`
— project_token is woven into each event's body by the node;
api_secret (optional) is used for the Basic-auth ``/import`` path.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.mixpanel.node import MixpanelNode

NODE = MixpanelNode

__all__ = ["NODE", "MixpanelNode"]
