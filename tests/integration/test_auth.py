"""Integration tests for the auth router."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.conftest import TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD

pytestmark = pytest.mark.integration


async def test_login_success(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_is_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email_is_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@nope.example", "password": "x"},
    )
    assert resp.status_code == 401


async def test_me_returns_current_user(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == TEST_ADMIN_EMAIL
    assert body["global_role"] == "owner"
    assert body["default_project_id"] is not None


async def test_refresh_rotates_token(client: AsyncClient) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
    )
    refresh_token = login.json()["refresh_token"]
    new_pair = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert new_pair.status_code == 200
    # Reusing the old refresh token must now fail:
    replay = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert replay.status_code == 401


async def test_me_without_token_is_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_bogus_token_is_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert resp.status_code == 401


async def test_request_id_roundtrips(client: AsyncClient) -> None:
    resp = await client.get("/healthz", headers={"X-Request-Id": "req_test_123"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-Id") == "req_test_123"


async def test_request_id_generated_when_missing(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-Id")  # non-empty id was generated
