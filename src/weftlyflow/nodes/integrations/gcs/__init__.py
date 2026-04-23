"""Google Cloud Storage integration — buckets and objects over JSON API.

Uses :class:`~weftlyflow.credentials.types.gcp_service_account.GcpServiceAccountCredential`.
The node exchanges the service-account JWT for a short-lived Bearer
via :func:`fetch_access_token` once per execution and reuses the same
token across the dispatch loop.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.gcs.node import GcsNode

NODE = GcsNode

__all__ = ["NODE", "GcsNode"]
