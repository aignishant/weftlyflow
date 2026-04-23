"""Rocket.Chat credential — ``X-Auth-Token`` + ``X-User-Id`` dual-header pair.

Rocket.Chat (https://developer.rocket.chat/apidocs/authentication) is
the only catalog provider that demands **two** authentication headers:
``X-Auth-Token: <token>`` identifies the personal-access token and
``X-User-Id: <id>`` identifies which user it belongs to. Omitting
either returns 401. There is no single-header shortcut.

Servers are self-hosted, so the credential also stores a configurable
``base_url`` (e.g. ``https://chat.example.com``) — not a fixed host.

The self-test calls ``GET <base_url>/api/v1/me`` which returns 200 +
the caller's profile on a valid pair.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_AUTH_TOKEN_HEADER: Final[str] = "X-Auth-Token"
_USER_ID_HEADER: Final[str] = "X-User-Id"
_TEST_PATH: Final[str] = "/api/v1/me"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class RocketChatApiCredential(BaseCredentialType):
    """Inject ``X-Auth-Token`` + ``X-User-Id`` (both mandatory)."""

    slug: ClassVar[str] = "weftlyflow.rocket_chat_api"
    display_name: ClassVar[str] = "Rocket.Chat API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.rocket.chat/apidocs/authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            required=True,
            description="Server root, e.g. https://chat.example.com (no trailing slash).",
        ),
        PropertySchema(
            name="user_id",
            display_name="User ID",
            type="string",
            required=True,
            description="User _id the personal-access token was issued for.",
        ),
        PropertySchema(
            name="auth_token",
            display_name="Personal Access Token",
            type="string",
            required=True,
            description="Personal-access token issued to the user.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``X-Auth-Token`` + ``X-User-Id`` on the outgoing request."""
        token = str(creds.get("auth_token", "")).strip()
        user_id = str(creds.get("user_id", "")).strip()
        request.headers[_AUTH_TOKEN_HEADER] = token
        request.headers[_USER_ID_HEADER] = user_id
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET <base_url>/api/v1/me`` and report the outcome."""
        base_url = str(creds.get("base_url") or "").strip().rstrip("/")
        user_id = str(creds.get("user_id") or "").strip()
        token = str(creds.get("auth_token") or "").strip()
        if not base_url:
            return CredentialTestResult(ok=False, message="base_url is empty")
        if not user_id or not token:
            return CredentialTestResult(ok=False, message="user_id and auth_token are required")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base_url}{_TEST_PATH}",
                    headers={
                        _AUTH_TOKEN_HEADER: token,
                        _USER_ID_HEADER: user_id,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"rocket.chat rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = RocketChatApiCredential
