"""Harvest integration — time entries, projects, users.

Uses :class:`~weftlyflow.credentials.types.harvest_api.HarvestApiCredential`
to inject Bearer auth alongside the mandatory ``Harvest-Account-ID``
scoping header on every call.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.harvest.node import HarvestNode

NODE = HarvestNode

__all__ = ["NODE", "HarvestNode"]
