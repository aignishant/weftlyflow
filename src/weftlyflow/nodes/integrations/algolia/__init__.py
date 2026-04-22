"""Algolia integration — Search v1 REST API for indices and records.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.algolia.node import AlgoliaNode

NODE = AlgoliaNode

__all__ = ["NODE", "AlgoliaNode"]
