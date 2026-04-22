"""Google Sheets integration — read/write ranges, append rows.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.google_sheets.node import GoogleSheetsNode

NODE = GoogleSheetsNode

__all__ = ["NODE", "GoogleSheetsNode"]
