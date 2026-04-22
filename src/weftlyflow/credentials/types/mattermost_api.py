"""Mattermost API credential — Bearer token + credential-owned base URL.

Mattermost (https://api.mattermost.com/) is self-hosted: every instance
lives at its own URL. This credential therefore carries both the
personal access token and the full base URL of the server (e.g.
``https://chat.acme.io``). Requests authenticate with a stock
``Authorization: Bearer <token>`` header; the node layer reads
:meth:`base_url_from` to resolve per-request URLs.

The self-test calls ``GET /api/v4/users/me`` which echoes the
authenticated user.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_VERSION_PREFIX: str = "/api/v4"
_TEST_PATH: str = "/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


def base_url_from(raw_base_url: str) -> str:
    """Normalize ``raw_base_url`` to ``https://host/api/v4``."""
    cleaned = raw_base_url.strip().rstrip("/")
    if not cleaned:
        msg = "Mattermost: 'base_url' is required"
        raise ValueError(msg)
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    if cleaned.endswith(_API_VERSION_PREFIX):
        return cleaned
    return f"{cleaned}{_API_VERSION_PREFIX}"


class MattermostApiCredential(BaseCredentialType):
    """Inject Bearer auth; pair the token with a self-hosted base URL."""

    slug: ClassVar[str] = "weftlyflow.mattermost_api"
    display_name: ClassVar[str] = "Mattermost API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.mattermost.com/integrate/reference/personal-access-token/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Mattermost personal access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            required=True,
            description="Server URL, e.g. 'https://chat.acme.io'.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <token>`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v4/users/me`` and report."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        try:
            base = base_url_from(str(creds.get("base_url") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_TEST_PATH}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"mattermost rejected token: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        username = ""
        if isinstance(payload, dict):
            username = str(payload.get("username", ""))
        suffix = f" as {username}" if username else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = MattermostApiCredential
