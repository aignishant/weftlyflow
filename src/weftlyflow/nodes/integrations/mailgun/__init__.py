"""Mailgun integration — transactional email via the v3 Messages API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.mailgun.node import MailgunNode

NODE = MailgunNode

__all__ = ["NODE", "MailgunNode"]
