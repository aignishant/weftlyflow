"""Pipedrive API credential — ``?api_token=`` query string + tenant host.

Pipedrive (https://developers.pipedrive.com/docs/api/v1) authenticates
every REST call by appending an ``api_token`` query parameter to the
URL; there is no ``Authorization`` header. Each company gets its own
subdomain (``https://<company>.pipedrive.com``), so the credential
carries both the token and the domain.

The self-test calls ``GET /users/me`` which echoes the authenticated
user.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_VERSION_PREFIX: str = "/api/v1"
_TEST_PATH: str = "/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


def base_url_for(company_domain: str) -> str:
    """Return the per-tenant base URL for ``company_domain``."""
    cleaned = company_domain.strip().lower().rstrip("/")
    if not cleaned:
        msg = "Pipedrive: 'company_domain' is required"
        raise ValueError(msg)
    host = cleaned if "." in cleaned else f"{cleaned}.pipedrive.com"
    return f"https://{host}{_API_VERSION_PREFIX}"


class PipedriveApiCredential(BaseCredentialType):
    """Append ``api_token`` to the URL; no header mutation."""

    slug: ClassVar[str] = "weftlyflow.pipedrive_api"
    display_name: ClassVar[str] = "Pipedrive API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.pipedrive.com/docs/api/v1/Authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_token",
            display_name="API Token",
            type="string",
            required=True,
            description="Personal API token from Pipedrive settings.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="company_domain",
            display_name="Company Domain",
            type="string",
            required=True,
            description="Subdomain or full host (e.g. 'acme' or 'acme.pipedrive.com').",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Append ``?api_token=<token>`` to the outgoing URL."""
        token = str(creds.get("api_token", ""))
        params = dict(request.url.params)
        params["api_token"] = token
        request.url = request.url.copy_with(params=params)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /users/me`` on the tenant host and report."""
        token = str(creds.get("api_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="api_token is empty")
        try:
            base = base_url_for(str(creds.get("company_domain") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_TEST_PATH}",
                    params={"api_token": token},
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"pipedrive rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = PipedriveApiCredential
