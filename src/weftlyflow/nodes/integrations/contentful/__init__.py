"""Contentful integration — Management (CMA) + Delivery (CDA) REST APIs.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.contentful.node import ContentfulNode

NODE = ContentfulNode

__all__ = ["NODE", "ContentfulNode"]
