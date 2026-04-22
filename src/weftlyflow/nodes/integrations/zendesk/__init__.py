"""Zendesk integration — Support v2 REST API for tickets and comments.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.zendesk.node import ZendeskNode

NODE = ZendeskNode

__all__ = ["NODE", "ZendeskNode"]
