"""Integration tests for the node-types catalog."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_list_node_types_returns_builtins(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/node-types", headers=auth_headers)
    assert resp.status_code == 200
    types = {item["type"] for item in resp.json()}
    # ``weftlyflow.code`` is gated behind ``WEFTLYFLOW_ENABLE_CODE_NODE`` and
    # intentionally absent from the default discovery set (spec §26 risk #2).
    assert types >= {
        "weftlyflow.manual_trigger",
        "weftlyflow.no_op",
        "weftlyflow.set",
        "weftlyflow.if",
    }


async def test_get_node_type_returns_latest(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/node-types/weftlyflow.if", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "weftlyflow.if"
    assert body["version"] == 1
    # The If node ships the predicate-operator options in its schema:
    operator_prop = next(p for p in body["properties"] if p["name"] == "operator")
    operator_values = {opt["value"] for opt in operator_prop["options"]}
    assert {"equals", "greater_than_or_equal", "is_empty"}.issubset(operator_values)


async def test_get_node_type_unknown_is_404(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    resp = await client.get(
        "/api/v1/node-types/weftlyflow.does_not_exist", headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_list_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/node-types")
    assert resp.status_code == 401
