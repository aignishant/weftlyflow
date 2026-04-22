"""HTTP Request node — issue an outbound HTTP call and emit the response."""

from __future__ import annotations

from weftlyflow.nodes.core.http_request.node import HttpRequestNode

NODE = HttpRequestNode

__all__ = ["NODE", "HttpRequestNode"]
