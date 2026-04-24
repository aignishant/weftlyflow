"""Authentication boundary probes.

Each test asserts that an attacker probe is *refused* — never 500, never
leaks a stack trace, never authenticates. These are seed probes; add to
them whenever a new auth path lands.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.security.conftest import TEST_ADMIN_EMAIL

pytestmark = pytest.mark.security


async def test_missing_bearer_token_is_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_tampered_jwt_is_401(client: AsyncClient, access_token: str) -> None:
    # Flip a character in the middle of the signature. The last base64
    # character of an HMAC-SHA256 only carries 4 bits plus 2 padding
    # bits, so flipping it can decode to the same signature — avoid.
    head, payload, sig = access_token.split(".")
    mid = len(sig) // 2
    bad_char = "A" if sig[mid] != "A" else "B"
    tampered_sig = sig[:mid] + bad_char + sig[mid + 1:]
    tampered = f"{head}.{payload}.{tampered_sig}"
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"},
    )
    assert resp.status_code == 401


async def test_bearer_scheme_required(client: AsyncClient, access_token: str) -> None:
    # Same token, but with the scheme stripped — must not authenticate.
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": access_token},
    )
    assert resp.status_code == 401


async def test_login_does_not_leak_user_enumeration(client: AsyncClient) -> None:
    # Wrong-password and unknown-email must return the same status with no
    # wording that distinguishes the two cases.
    wrong_pw = await client.post(
        "/api/v1/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": "wrong"},
    )
    unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@nope.example", "password": "x"},
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()
