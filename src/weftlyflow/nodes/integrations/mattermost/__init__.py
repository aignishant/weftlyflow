"""Mattermost integration — v4 REST API for self-hosted chat.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.mattermost.node import MattermostNode

NODE = MattermostNode

__all__ = ["NODE", "MattermostNode"]
