"""Datadog integration — events, monitors, metric queries.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.datadog.node import DatadogNode

NODE = DatadogNode

__all__ = ["NODE", "DatadogNode"]
