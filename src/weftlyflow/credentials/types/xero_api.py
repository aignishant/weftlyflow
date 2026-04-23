"""Xero credential — OAuth2 Bearer token paired with a mandatory tenant header.

Xero (https://developer.xero.com/documentation/guides/oauth2/auth-flow/)
authenticates with ``Authorization: Bearer <access_token>``, but the
distinctive shape is the *mandatory* ``xero-tenant-id`` header — a
single Xero app can be connected to many organisations, and every
request must declare which one. Sending the Bearer without the tenant
header returns HTTP 403 even on well-scoped keys.

This credential therefore carries the access token and the tenant id
as a pair; omitting either renders the credential unusable. The
self-test calls ``GET /connections`` on the Identity API which accepts
the Bearer alone and returns the list of tenants the token can access.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_CONNECTIONS_URL: str = "https://api.xero.com/connections"
_TEST_TIMEOUT_SECONDS: float = 10.0
_TENANT_HEADER: str = "xero-tenant-id"


class XeroApiCredential(BaseCredentialType):
    """Inject Bearer + mandatory ``xero-tenant-id`` scoping header."""

    slug: ClassVar[str] = "weftlyflow.xero_api"
    display_name: ClassVar[str] = "Xero API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.xero.com/documentation/guides/oauth2/auth-flow/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Xero OAuth2 access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="tenant_id",
            display_name="Tenant ID",
            type="string",
            required=True,
            description="Xero tenant (organisation) UUID — one token can span many.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer auth + mandatory ``xero-tenant-id`` header."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        tenant_id = str(creds.get("tenant_id", "")).strip()
        if tenant_id:
            request.headers[_TENANT_HEADER] = tenant_id
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /connections`` and report the outcome."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        tenant_id = str(creds.get("tenant_id") or "").strip()
        if not tenant_id:
            return CredentialTestResult(ok=False, message="tenant_id is empty")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(_CONNECTIONS_URL, headers=headers)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"xero rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = XeroApiCredential
