"""Integration tests for the ``/metrics`` Prometheus scrape endpoint.

Covers both the normal-on path (200 + text/plain response in the exposition
format) and the disabled path (404 — not 403, to keep the endpoint
invisible rather than leak its existence).
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient

from weftlyflow.config import get_settings
from weftlyflow.observability import metrics


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_exposition(client: AsyncClient) -> None:
    metrics.executions_total.labels(status="success", mode="webhook").inc()

    resp = await client.get("/metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "weftlyflow_executions_total" in body


@pytest.mark.asyncio
async def test_metrics_endpoint_is_404_when_disabled(client: AsyncClient) -> None:
    os.environ["WEFTLYFLOW_METRICS_ENABLED"] = "false"
    get_settings.cache_clear()
    try:
        resp = await client.get("/metrics")
        assert resp.status_code == 404
    finally:
        os.environ.pop("WEFTLYFLOW_METRICS_ENABLED", None)
        get_settings.cache_clear()
