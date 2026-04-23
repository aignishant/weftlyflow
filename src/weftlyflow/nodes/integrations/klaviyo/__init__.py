"""Klaviyo integration — events, profiles, list membership.

Uses :class:`~weftlyflow.credentials.types.klaviyo_api.KlaviyoApiCredential`
to inject the custom ``Klaviyo-API-Key`` scheme and mandatory
``revision`` header on every call.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.klaviyo.node import KlaviyoNode

NODE = KlaviyoNode

__all__ = ["NODE", "KlaviyoNode"]
