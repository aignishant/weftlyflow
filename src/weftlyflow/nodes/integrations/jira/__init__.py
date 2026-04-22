"""Jira integration — Cloud v3 REST API for issue tracking.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.jira.node import JiraNode

NODE = JiraNode

__all__ = ["NODE", "JiraNode"]
