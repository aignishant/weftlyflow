"""Cloudflare integration — client/v4 REST API for zones and DNS records.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.cloudflare.node import CloudflareNode

NODE = CloudflareNode

__all__ = ["NODE", "CloudflareNode"]
