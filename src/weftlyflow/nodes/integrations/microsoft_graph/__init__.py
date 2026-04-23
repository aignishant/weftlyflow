"""Microsoft Graph integration — directory + Outlook + calendar via OData.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.microsoft_graph.node import MicrosoftGraphNode

NODE = MicrosoftGraphNode

__all__ = ["NODE", "MicrosoftGraphNode"]
