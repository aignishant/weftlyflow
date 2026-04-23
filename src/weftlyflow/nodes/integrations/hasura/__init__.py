"""Hasura integration — GraphQL queries/mutations over HTTP.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.hasura.node import HasuraNode

NODE = HasuraNode

__all__ = ["NODE", "HasuraNode"]
