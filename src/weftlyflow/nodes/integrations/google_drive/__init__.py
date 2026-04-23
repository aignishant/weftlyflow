"""Google Drive integration — files and folders via the Drive v3 API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.google_drive.node import GoogleDriveNode

NODE = GoogleDriveNode

__all__ = ["NODE", "GoogleDriveNode"]
