"""Apple App Store Connect integration — apps, builds, testers.

Uses :class:`~weftlyflow.credentials.types.asc_api.AscApiCredential`
which mints a fresh ES256 JWT on every call. The node itself stays
declarative — all cryptographic concerns live in the credential.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.asc.node import AscNode

NODE = AscNode

__all__ = ["NODE", "AscNode"]
