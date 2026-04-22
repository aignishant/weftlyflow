"""SendGrid integration — transactional email via the v3 Mail Send API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.sendgrid.node import SendGridNode

NODE = SendGridNode

__all__ = ["NODE", "SendGridNode"]
