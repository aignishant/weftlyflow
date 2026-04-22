"""HubSpot Private-App credential — Bearer token for CRM v3 endpoints.

HubSpot Private Apps (https://developers.hubspot.com/docs/api/private-apps)
issue a long-lived access token scoped to a single account. The token is
sent as ``Authorization: Bearer <token>``. This credential type is a
thin, HubSpot-branded wrapper so UIs can steer users to the correct
token-generation flow and the self-test hits a HubSpot endpoint
(``GET /crm/v3/owners``) rather than a generic one.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_OWNERS_URL: str = "https://api.hubapi.com/crm/v3/owners"
_TEST_TIMEOUT_SECONDS: float = 10.0


class HubSpotPrivateAppCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer <access_token>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.hubspot_private_app"
    display_name: ClassVar[str] = "HubSpot Private App"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://developers.hubspot.com/docs/api/private-apps"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Private-app access token from the HubSpot settings page.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <access_token>`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /crm/v3/owners`` and report the outcome."""
        token = str(creds.get("access_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _OWNERS_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"limit": 1},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"hubspot rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = HubSpotPrivateAppCredential
