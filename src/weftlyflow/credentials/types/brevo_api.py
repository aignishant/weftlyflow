"""Brevo API credential — ``api-key`` lowercase header.

Brevo (formerly Sendinblue, https://developers.brevo.com/reference/)
authenticates via a custom lowercase ``api-key`` header — distinct from
the ``X-API-Key`` convention other services use. The self-test calls
``GET /v3/account`` which echoes the account profile.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_ACCOUNT_URL: str = "https://api.brevo.com/v3/account"
_TEST_TIMEOUT_SECONDS: float = 10.0


class BrevoApiCredential(BaseCredentialType):
    """Inject ``api-key: <api_key>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.brevo_api"
    display_name: ClassVar[str] = "Brevo API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.brevo.com/docs/getting-started"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Brevo v3 API key (starts with 'xkeysib-').",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``api-key: <api_key>`` on ``request``."""
        key = str(creds.get("api_key", "")).strip()
        request.headers["api-key"] = key
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v3/account`` and report the outcome."""
        key = str(creds.get("api_key", "")).strip()
        if not key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(_ACCOUNT_URL, headers={"api-key": key})
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"brevo rejected key: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        email = ""
        if isinstance(payload, dict):
            email = str(payload.get("email", ""))
        suffix = f" as {email}" if email else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = BrevoApiCredential
