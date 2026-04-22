"""Intercom API credential — Bearer token + required ``Intercom-Version``.

Intercom's REST API (https://developers.intercom.com/docs/references/rest-api)
uses a standard OAuth-style ``Authorization: Bearer`` token, but every
request must also pin an API version via ``Intercom-Version: 2.11`` (or
similar). Shipping the version on the credential means workflows declare
once which Intercom API surface they target, instead of repeating it on
every node.

The self-test calls ``GET https://api.intercom.io/me`` which echoes the
authenticated admin.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: str = "https://api.intercom.io"
_DEFAULT_VERSION: str = "2.11"
_TEST_TIMEOUT_SECONDS: float = 10.0


class IntercomApiCredential(BaseCredentialType):
    """Inject Bearer token and ``Intercom-Version`` on every request."""

    slug: ClassVar[str] = "weftlyflow.intercom_api"
    display_name: ClassVar[str] = "Intercom API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.intercom.com/docs/references/rest-api/authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Intercom access token (from Developer Hub).",
            type_options={"password": True},
        ),
        PropertySchema(
            name="api_version",
            display_name="API Version",
            type="string",
            default=_DEFAULT_VERSION,
            description="Intercom API version header value.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer token and ``Intercom-Version`` header on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        version = str(creds.get("api_version") or _DEFAULT_VERSION).strip() or _DEFAULT_VERSION
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["Intercom-Version"] = version
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /me`` and report the outcome."""
        token = str(creds.get("access_token", "")).strip()
        version = str(creds.get("api_version") or _DEFAULT_VERSION).strip() or _DEFAULT_VERSION
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}/me",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Intercom-Version": version,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"intercom rejected token: HTTP {response.status_code}",
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


TYPE = IntercomApiCredential
