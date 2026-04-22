"""Okta integration — v1 REST API for user and group management.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.okta.node import OktaNode

NODE = OktaNode

__all__ = ["NODE", "OktaNode"]
