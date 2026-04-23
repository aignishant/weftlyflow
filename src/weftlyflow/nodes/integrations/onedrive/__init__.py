"""OneDrive integration — files via Microsoft Graph /me/drive endpoints.

Reuses the ``microsoft_graph`` credential rather than shipping a
OneDrive-specific OAuth2 flavour; Graph's ``/me/drive/*`` surface
already serves personal OneDrive, OneDrive for Business, and SharePoint
drives.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.onedrive.node import OneDriveNode

NODE = OneDriveNode

__all__ = ["NODE", "OneDriveNode"]
