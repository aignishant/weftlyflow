"""Brevo integration — v3 REST API for transactional email and contacts.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.brevo.node import BrevoNode

NODE = BrevoNode

__all__ = ["NODE", "BrevoNode"]
