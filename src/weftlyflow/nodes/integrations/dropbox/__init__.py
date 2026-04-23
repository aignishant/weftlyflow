"""Dropbox integration — files and folders via RPC + content endpoints.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.dropbox.node import DropboxNode

NODE = DropboxNode

__all__ = ["NODE", "DropboxNode"]
