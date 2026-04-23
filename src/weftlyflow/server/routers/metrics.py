"""Prometheus scrape endpoint.

Exposes ``GET /metrics`` when ``settings.metrics_enabled`` is true. The
response body is the standard Prometheus text exposition format; no
authentication is applied because the expected deployment topology is a
private network scrape from the cluster's metrics server.

If you need to expose this endpoint over a public URL, put it behind an
auth middleware — Prometheus metric names and label values can leak
workflow topology.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from weftlyflow.config import get_settings
from weftlyflow.observability import metrics

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Prometheus scrape endpoint")
async def prometheus_metrics() -> Response:
    """Return the current metric snapshot in Prometheus text format.

    Raises:
        HTTPException: ``404`` when metrics are disabled — keeps the
            endpoint invisible rather than returning 403, which would
            leak its existence.
    """
    if not get_settings().metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    body, content_type = metrics.render_latest()
    return Response(content=body, media_type=content_type)
