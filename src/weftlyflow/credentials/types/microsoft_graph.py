"""Microsoft Graph credential — Bearer access token for a specific tenant.

Microsoft Graph (https://learn.microsoft.com/en-us/graph/overview) is
multi-tenant by construction: a token obtained from the Microsoft
identity platform is always scoped to a single Azure AD tenant, and
operators routinely audit *which* tenant a credential belongs to. This
credential stores the tenant identifier alongside the Bearer token —
it does not travel on the wire (Graph reads the tenant from the
token's ``tid`` claim) but keeps the operator contract explicit.

The self-test calls ``GET /v1.0/me``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_URL: str = "https://graph.microsoft.com/v1.0/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


class MicrosoftGraphCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer <access_token>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.microsoft_graph"
    display_name: ClassVar[str] = "Microsoft Graph"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://learn.microsoft.com/en-us/graph/overview"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Microsoft identity platform OAuth2 access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="tenant_id",
            display_name="Tenant ID",
            type="string",
            required=True,
            description="Azure AD tenant the token was issued against.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <access_token>``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v1.0/me`` and report."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        tenant = str(creds.get("tenant_id") or "").strip()
        if not tenant:
            return CredentialTestResult(ok=False, message="tenant_id is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _TEST_URL,
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
                message=f"microsoft graph rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = MicrosoftGraphCredential
