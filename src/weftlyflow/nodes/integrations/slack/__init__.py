"""Slack integration — post/update/delete messages, list channels.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.slack.node import SlackNode

NODE = SlackNode

__all__ = ["NODE", "SlackNode"]
