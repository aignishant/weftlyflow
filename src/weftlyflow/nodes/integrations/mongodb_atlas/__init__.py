"""MongoDB Atlas integration — projects, clusters, database users.

Uses :class:`~weftlyflow.credentials.types.mongodb_atlas_api.MongoDbAtlasApiCredential`.
HTTP Digest auth is applied at the :class:`httpx.AsyncClient` level because
Digest requires a challenge/response handshake — no header can be computed
ahead of time. The node therefore bypasses the usual ``inject`` pathway and
constructs the client with :class:`httpx.DigestAuth` directly.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.mongodb_atlas.node import MongoDbAtlasNode

NODE = MongoDbAtlasNode

__all__ = ["NODE", "MongoDbAtlasNode"]
