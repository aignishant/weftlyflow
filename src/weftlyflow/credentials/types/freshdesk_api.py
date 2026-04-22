"""Freshdesk API credential — Basic auth with api_key + dummy password.

Freshdesk (https://developers.freshdesk.com/api/) authenticates with
HTTP Basic auth where the username is the personal API key and the
password is a literal ``X`` — a convention Freshdesk explicitly
documents. Every customer gets their own subdomain
(``https://<subdomain>.freshdesk.com``), so the credential carries
both the key and the subdomain.

The self-test calls ``GET /api/v2/agents/me`` which echoes the
authenticated agent.
"""

from __future__ import annotations

from base64 import b64encode
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_VERSION_PREFIX: str = "/api/v2"
_TEST_PATH: str = "/agents/me"
_TEST_TIMEOUT_SECONDS: float = 10.0
_BASIC_PASSWORD: str = "X"


def base_url_for(subdomain: str) -> str:
    """Return the per-tenant base URL for ``subdomain``."""
    cleaned = subdomain.strip().lower().rstrip("/")
    if not cleaned:
        msg = "Freshdesk: 'subdomain' is required"
        raise ValueError(msg)
    host = cleaned if "." in cleaned else f"{cleaned}.freshdesk.com"
    return f"https://{host}{_API_VERSION_PREFIX}"


def basic_auth_header(api_key: str) -> str:
    """Return the ``Authorization`` header value for ``api_key``."""
    pair = f"{api_key}:{_BASIC_PASSWORD}".encode()
    return "Basic " + b64encode(pair).decode("ascii")


class FreshdeskApiCredential(BaseCredentialType):
    """Inject Basic auth with api_key as username + ``X`` as password."""

    slug: ClassVar[str] = "weftlyflow.freshdesk_api"
    display_name: ClassVar[str] = "Freshdesk API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.freshdesk.com/api/#authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Personal API key from Freshdesk profile settings.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="subdomain",
            display_name="Subdomain",
            type="string",
            required=True,
            description="Subdomain or full host (e.g. 'acme' or 'acme.freshdesk.com').",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Basic base64(api_key:X)`` on ``request``."""
        api_key = str(creds.get("api_key", "")).strip()
        request.headers["Authorization"] = basic_auth_header(api_key)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v2/agents/me`` on the tenant host and report."""
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            base = base_url_for(str(creds.get("subdomain") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_TEST_PATH}",
                    headers={
                        "Authorization": basic_auth_header(api_key),
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"freshdesk rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = FreshdeskApiCredential
