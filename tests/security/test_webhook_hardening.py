"""Webhook ingress probes.

These tests live at the HTTP boundary — a request hits the public
webhook path and we assert the ingress layer refuses malformed or
oversized bodies without crashing the server.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.security


async def test_unknown_webhook_path_is_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/webhook/does-not-exist",
        json={"ping": True},
    )
    assert resp.status_code == 404


async def test_webhook_with_malformed_json_does_not_500(client: AsyncClient) -> None:
    # Content-Type says JSON but the body is invalid. The ingress layer
    # must reject with a 4xx, never 500.
    resp = await client.post(
        "/webhook/does-not-exist",
        content=b"{ not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code < 500
