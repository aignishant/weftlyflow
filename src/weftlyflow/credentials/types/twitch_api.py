"""Twitch Helix API credential — Bearer token plus mandatory ``Client-Id``.

Twitch (https://dev.twitch.tv/docs/api/) rejects any Helix request that
does not carry *both* ``Authorization: Bearer <access_token>`` and the
registered application's ``Client-Id`` header. The Client-Id is a
public identifier (it is checked against the token's owning app) but
is required on every call — so this credential stores it alongside
the OAuth2 access token and injects both on the wire.

The self-test calls ``GET /helix/users`` (no query → returns the
token's owner) which round-trips both headers.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_URL: str = "https://api.twitch.tv/helix/users"
_TEST_TIMEOUT_SECONDS: float = 10.0


class TwitchApiCredential(BaseCredentialType):
    """Inject the ``Authorization: Bearer`` + ``Client-Id`` header pair."""

    slug: ClassVar[str] = "weftlyflow.twitch_api"
    display_name: ClassVar[str] = "Twitch API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://dev.twitch.tv/docs/api/"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Twitch OAuth2 access token (app or user).",
            type_options={"password": True},
        ),
        PropertySchema(
            name="client_id",
            display_name="Client ID",
            type="string",
            required=True,
            description="Registered Twitch application Client ID.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set both ``Authorization`` and ``Client-Id`` headers."""
        token = str(creds.get("access_token", "")).strip()
        client_id = str(creds.get("client_id", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["Client-Id"] = client_id
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /helix/users`` and report."""
        token = str(creds.get("access_token") or "").strip()
        client_id = str(creds.get("client_id") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        if not client_id:
            return CredentialTestResult(ok=False, message="client_id is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _TEST_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Client-Id": client_id,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"twitch rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = TwitchApiCredential
