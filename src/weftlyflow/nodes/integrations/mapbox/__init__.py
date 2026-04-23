"""Mapbox integration — geocoding, directions, matrix, isochrone.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.mapbox.node import MapboxNode

NODE = MapboxNode

__all__ = ["NODE", "MapboxNode"]
