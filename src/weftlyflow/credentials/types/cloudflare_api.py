"""Cloudflare API credential — dual ``X-Auth-Email`` + ``X-Auth-Key`` headers.

Cloudflare's legacy Global-API-Key authentication scheme
(https://developers.cloudflare.com/fundamentals/api/get-started/ca-keys/)
requires *two* custom headers on every request: the account owner's
email in ``X-Auth-Email`` and the key itself in ``X-Auth-Key``. The
scheme is explicitly *not* ``Authorization: Bearer``; Cloudflare's
newer scoped API tokens use Bearer and are intentionally out of scope
here (we cover the dual-header case to diversify auth coverage).

The self-test calls ``GET /user`` which echoes the authenticated user.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: str = "https://api.cloudflare.com/client/v4"
_TEST_PATH: str = "/user"
_TEST_TIMEOUT_SECONDS: float = 10.0


class CloudflareApiCredential(BaseCredentialType):
    """Inject the ``X-Auth-Email`` + ``X-Auth-Key`` header pair."""

    slug: ClassVar[str] = "weftlyflow.cloudflare_api"
    display_name: ClassVar[str] = "Cloudflare API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.cloudflare.com/fundamentals/api/get-started/ca-keys/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_email",
            display_name="Account Email",
            type="string",
            required=True,
            description="Email address of the Cloudflare account owner.",
        ),
        PropertySchema(
            name="api_key",
            display_name="Global API Key",
            type="string",
            required=True,
            description="Global API key from the Cloudflare dashboard.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set both ``X-Auth-Email`` and ``X-Auth-Key`` headers."""
        request.headers["X-Auth-Email"] = str(creds.get("api_email", "")).strip()
        request.headers["X-Auth-Key"] = str(creds.get("api_key", "")).strip()
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /user`` and report."""
        email = str(creds.get("api_email") or "").strip()
        key = str(creds.get("api_key") or "").strip()
        if not email:
            return CredentialTestResult(ok=False, message="api_email is empty")
        if not key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}{_TEST_PATH}",
                    headers={
                        "X-Auth-Email": email,
                        "X-Auth-Key": key,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"cloudflare rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = CloudflareApiCredential
