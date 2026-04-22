"""Mailchimp integration — Marketing v3 REST API for lists and members.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.mailchimp.node import MailchimpNode

NODE = MailchimpNode

__all__ = ["NODE", "MailchimpNode"]
