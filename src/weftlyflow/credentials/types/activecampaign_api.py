"""ActiveCampaign credential — raw ``Api-Token`` header + per-account URL.

ActiveCampaign (https://developers.activecampaign.com/reference/authentication)
is a multi-tenant SaaS where each account gets its own subdomain
(e.g. ``https://acme-55.api-us1.com``). Authentication uses a raw
``Api-Token`` header — *not* ``Authorization: Bearer`` — carrying the
API token verbatim with no prefix. The distinctive shape here is the
combination of the raw header name and the per-tenant base URL, which
together mean the credential has to ship *both* pieces of information
for nodes to stay host-agnostic.

The self-test calls ``GET /api/3/users/me``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_TOKEN_HEADER: str = "Api-Token"
_API_VERSION_PREFIX: str = "/api/3"
_TEST_PATH: str = "/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


def base_url_from(raw_url: str) -> str:
    """Normalize ``raw_url`` to ``https://<tenant>/api/3``.

    Accepts bare hostnames, full URLs, and URLs already ending in the
    ``/api/3`` prefix.
    """
    cleaned = raw_url.strip().rstrip("/")
    if not cleaned:
        msg = "ActiveCampaign: 'api_url' is required"
        raise ValueError(msg)
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    if cleaned.endswith(_API_VERSION_PREFIX):
        return cleaned
    return f"{cleaned}{_API_VERSION_PREFIX}"


class ActiveCampaignApiCredential(BaseCredentialType):
    """Inject raw ``Api-Token`` header paired with a per-tenant base URL."""

    slug: ClassVar[str] = "weftlyflow.activecampaign_api"
    display_name: ClassVar[str] = "ActiveCampaign API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.activecampaign.com/reference/authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_url",
            display_name="API URL",
            type="string",
            required=True,
            description="Account URL, e.g. 'https://acme-55.api-us1.com'.",
        ),
        PropertySchema(
            name="api_token",
            display_name="API Token",
            type="string",
            required=True,
            description="Raw API token from Settings > Developer.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set the raw ``Api-Token`` header on ``request``."""
        token = str(creds.get("api_token", "")).strip()
        request.headers[_API_TOKEN_HEADER] = token
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/3/users/me`` and report."""
        token = str(creds.get("api_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="api_token is empty")
        try:
            base = base_url_from(str(creds.get("api_url") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_TEST_PATH}",
                    headers={
                        _API_TOKEN_HEADER: token,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"activecampaign rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = ActiveCampaignApiCredential
