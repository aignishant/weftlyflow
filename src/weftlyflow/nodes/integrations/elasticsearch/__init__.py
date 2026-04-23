"""Elasticsearch integration — search, index, bulk operations.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.elasticsearch.node import ElasticsearchNode

NODE = ElasticsearchNode

__all__ = ["NODE", "ElasticsearchNode"]
