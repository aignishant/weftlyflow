"""Azure Blob Storage integration — container + blob ops with SharedKey signing.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.azure_blob.node import AzureBlobNode

NODE = AzureBlobNode

__all__ = ["NODE", "AzureBlobNode"]
