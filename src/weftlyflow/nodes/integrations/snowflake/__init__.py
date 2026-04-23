"""Snowflake integration — SQL API v2 execute + async polling.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.snowflake.node import SnowflakeNode

NODE = SnowflakeNode

__all__ = ["NODE", "SnowflakeNode"]
