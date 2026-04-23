"""Gmail integration — send and read messages via the Gmail API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.gmail.node import GmailNode

NODE = GmailNode

__all__ = ["NODE", "GmailNode"]
