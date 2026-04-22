"""Twilio integration — SMS / MMS via the Programmable Messaging REST API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.twilio.node import TwilioNode

NODE = TwilioNode

__all__ = ["NODE", "TwilioNode"]
