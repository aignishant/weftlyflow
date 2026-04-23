"""QuickBooks Online credential — OAuth2 Bearer paired with a realmId + environment.

QuickBooks (https://developer.intuit.com/app/developer/qbo/docs/develop/
authentication-and-authorization/oauth-2.0) authenticates with
``Authorization: Bearer <access_token>`` — but that alone is *not*
enough to address any resource. Every REST call embeds the tenant
(``realmId``, Intuit's company id) directly in the URL **path** —
``/v3/company/{realmId}/...`` — and the environment determines the
host: ``sandbox-quickbooks.api.intuit.com`` vs ``quickbooks.api.intuit.com``.

This credential therefore carries four values: access token, realmId,
environment (``sandbox`` / ``production``), and an optional minor
version. Per-tenant URL scoping via *path* distinguishes it from
header-based tenant scoping (Xero) and from per-tenant host scoping
(ActiveCampaign, NetSuite).

The self-test calls ``GET /v3/company/{realmId}/companyinfo/{realmId}``
which returns 200 with company metadata on valid keys.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_PRODUCTION_HOST: Final[str] = "quickbooks.api.intuit.com"
_SANDBOX_HOST: Final[str] = "sandbox-quickbooks.api.intuit.com"
_ENV_SANDBOX: Final[str] = "sandbox"
_ENV_PRODUCTION: Final[str] = "production"
_VALID_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {_ENV_SANDBOX, _ENV_PRODUCTION},
)
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def host_from(environment: str) -> str:
    """Return the QuickBooks host for ``environment``."""
    cleaned = environment.strip().lower()
    if cleaned not in _VALID_ENVIRONMENTS:
        msg = (
            f"QuickBooks: 'environment' must be one of "
            f"{sorted(_VALID_ENVIRONMENTS)!r}"
        )
        raise ValueError(msg)
    return _SANDBOX_HOST if cleaned == _ENV_SANDBOX else _PRODUCTION_HOST


class QuickBooksOAuth2Credential(BaseCredentialType):
    """Inject Bearer auth — tenant scoping is in the URL path."""

    slug: ClassVar[str] = "weftlyflow.quickbooks_oauth2"
    display_name: ClassVar[str] = "QuickBooks Online OAuth2"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.intuit.com/app/developer/qbo/docs/develop/"
        "authentication-and-authorization/oauth-2.0"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="QuickBooks OAuth2 access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="realm_id",
            display_name="Realm ID",
            type="string",
            required=True,
            description="QuickBooks company id — embedded in every request path.",
        ),
        PropertySchema(
            name="environment",
            display_name="Environment",
            type="string",
            required=True,
            default=_ENV_PRODUCTION,
            description="'sandbox' or 'production'.",
        ),
        PropertySchema(
            name="minor_version",
            display_name="Minor Version",
            type="string",
            required=False,
            description="Optional 'minorversion' query param pin.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <access_token>`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v3/company/{realmId}/companyinfo/{realmId}`` and report."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        realm_id = str(creds.get("realm_id") or "").strip()
        if not realm_id:
            return CredentialTestResult(ok=False, message="realm_id is empty")
        try:
            host = host_from(str(creds.get("environment") or _ENV_PRODUCTION))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        url = f"https://{host}/v3/company/{realm_id}/companyinfo/{realm_id}"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
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
                message=f"quickbooks rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = QuickBooksOAuth2Credential
