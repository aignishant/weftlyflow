"""Zendesk API credential — Basic auth with ``/token`` username suffix.

Zendesk's REST API (https://developer.zendesk.com/api-reference/) signs
requests with HTTP Basic auth, but the username is the admin email with
``/token`` appended and the password is the API token itself — e.g.
``admin@acme.com/token:<api_token>``. The host is tenant-specific
(``<subdomain>.zendesk.com``), so the subdomain lives on the credential.

The self-test calls ``GET /api/v2/users/me.json`` which every valid
token can read.
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_PATH: str = "/api/v2/users/me.json"
_TEST_TIMEOUT_SECONDS: float = 10.0


class ZendeskApiCredential(BaseCredentialType):
    """Inject ``Authorization: Basic base64(email/token:api_token)``."""

    slug: ClassVar[str] = "weftlyflow.zendesk_api"
    display_name: ClassVar[str] = "Zendesk API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.zendesk.com/api-reference/introduction/security-and-auth/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="subdomain",
            display_name="Subdomain",
            type="string",
            required=True,
            description="Zendesk subdomain — 'acme' for acme.zendesk.com.",
            placeholder="acme",
        ),
        PropertySchema(
            name="email",
            display_name="Admin Email",
            type="string",
            required=True,
            description="Email of the admin whose API token is used.",
        ),
        PropertySchema(
            name="api_token",
            display_name="API Token",
            type="string",
            required=True,
            description="API token generated in Zendesk Admin Center.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Basic auth with ``<email>/token`` as username."""
        email = str(creds.get("email", "")).strip()
        token = str(creds.get("api_token", "")).strip()
        encoded = base64.b64encode(f"{email}/token:{token}".encode()).decode("ascii")
        request.headers["Authorization"] = f"Basic {encoded}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v2/users/me.json`` and report the outcome."""
        subdomain = str(creds.get("subdomain") or "").strip().lower()
        email = str(creds.get("email", "")).strip()
        token = str(creds.get("api_token", "")).strip()
        if not subdomain:
            return CredentialTestResult(ok=False, message="subdomain is empty")
        if not email:
            return CredentialTestResult(ok=False, message="email is empty")
        if not token:
            return CredentialTestResult(ok=False, message="api_token is empty")
        encoded = base64.b64encode(f"{email}/token:{token}".encode()).decode("ascii")
        url = f"https://{subdomain}.zendesk.com{_TEST_PATH}"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url, headers={"Authorization": f"Basic {encoded}"},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"zendesk rejected token: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        name = ""
        if isinstance(payload, dict):
            user = payload.get("user")
            if isinstance(user, dict):
                name = str(user.get("name", ""))
        suffix = f" as {name}" if name else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = ZendeskApiCredential
