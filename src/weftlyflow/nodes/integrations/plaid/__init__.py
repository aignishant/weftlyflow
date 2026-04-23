"""Plaid integration — link tokens, items, accounts, transaction sync.

Uses :class:`~weftlyflow.credentials.types.plaid_api.PlaidApiCredential`.
The client_id + secret pair is folded into every request body by the
node; the credential's environment field selects sandbox /
development / production host.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.plaid.node import PlaidNode

NODE = PlaidNode

__all__ = ["NODE", "PlaidNode"]
