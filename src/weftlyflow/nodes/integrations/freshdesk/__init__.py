"""Freshdesk integration — helpdesk v2 REST API for tickets and contacts.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.freshdesk.node import FreshdeskNode

NODE = FreshdeskNode

__all__ = ["NODE", "FreshdeskNode"]
