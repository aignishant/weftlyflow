"""ClickUp API credential — **unprefixed** ``Authorization`` header.

Unlike every other OAuth2/Bearer-style service, ClickUp
(https://clickup.com/api) wants the token sent **raw** — just
``Authorization: pk_XXXX`` with no ``Bearer`` or ``Bot`` prefix. This
credential type exists to capture that one wrinkle cleanly rather than
relying on a generic bearer type.

The self-test calls ``GET /api/v2/user`` which echoes the authenticated
user's profile.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_USER_URL: str = "https://api.clickup.com/api/v2/user"
_TEST_TIMEOUT_SECONDS: float = 10.0


class ClickUpApiCredential(BaseCredentialType):
    """Inject ``Authorization: <token>`` (no prefix) on every request."""

    slug: ClassVar[str] = "weftlyflow.clickup_api"
    display_name: ClassVar[str] = "ClickUp API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://clickup.com/api/developer-portal/authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_token",
            display_name="API Token",
            type="string",
            required=True,
            description="Personal token from ClickUp settings (starts with 'pk_').",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set raw ``Authorization: <api_token>`` on ``request``."""
        token = str(creds.get("api_token", "")).strip()
        request.headers["Authorization"] = token
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v2/user`` and report the outcome."""
        token = str(creds.get("api_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="api_token is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(_USER_URL, headers={"Authorization": token})
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"clickup rejected token: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        username = ""
        if isinstance(payload, dict):
            user = payload.get("user")
            if isinstance(user, dict):
                username = str(user.get("username", ""))
        suffix = f" as {username}" if username else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = ClickUpApiCredential
