"""Zoho CRM credential — ``Zoho-oauthtoken`` prefix + DC-aware host.

Zoho's CRM API (https://www.zoho.com/crm/developer/docs/api/v6/) uses
the custom authorization scheme ``Authorization: Zoho-oauthtoken
<access_token>`` (notably *not* ``Bearer``). Access tokens are
short-lived; workflows that rely on refresh must bring their own
refresh loop — this credential stores the pre-issued access token and
the datacenter segment that dictates the API host.

Datacenter suffixes map 1:1 to Zoho's published hosts:

* ``us``  → ``www.zohoapis.com``
* ``eu``  → ``www.zohoapis.eu``
* ``in``  → ``www.zohoapis.in``
* ``au``  → ``www.zohoapis.com.au``
* ``jp``  → ``www.zohoapis.jp``
* ``cn``  → ``www.zohoapis.com.cn``

The self-test calls ``GET /crm/v6/org`` which echoes the connected
organization.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertyOption, PropertySchema

DATACENTER_HOSTS: Final[dict[str, str]] = {
    "us": "www.zohoapis.com",
    "eu": "www.zohoapis.eu",
    "in": "www.zohoapis.in",
    "au": "www.zohoapis.com.au",
    "jp": "www.zohoapis.jp",
    "cn": "www.zohoapis.com.cn",
}
_DEFAULT_DATACENTER: str = "us"
_TEST_PATH: str = "/crm/v6/org"
_TEST_TIMEOUT_SECONDS: float = 10.0


def host_for(datacenter: str) -> str:
    """Return the API host for ``datacenter`` or raise :class:`ValueError`."""
    key = datacenter.strip().lower()
    if key not in DATACENTER_HOSTS:
        msg = f"Zoho: unknown datacenter {datacenter!r}"
        raise ValueError(msg)
    return DATACENTER_HOSTS[key]


class ZohoCrmOAuth2Credential(BaseCredentialType):
    """Inject ``Authorization: Zoho-oauthtoken <token>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.zoho_crm_oauth2"
    display_name: ClassVar[str] = "Zoho CRM OAuth2"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://www.zoho.com/crm/developer/docs/api/v6/auth-request.html"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Pre-issued Zoho OAuth2 access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="datacenter",
            display_name="Datacenter",
            type="options",
            default=_DEFAULT_DATACENTER,
            required=True,
            options=[
                PropertyOption(value=dc, label=dc.upper())
                for dc in DATACENTER_HOSTS
            ],
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Zoho-oauthtoken <token>`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Zoho-oauthtoken {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /crm/v6/org`` on the tenant DC host and report."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        datacenter = str(creds.get("datacenter") or _DEFAULT_DATACENTER).strip().lower()
        try:
            host = host_for(datacenter)
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        url = f"https://{host}{_TEST_PATH}"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": f"Zoho-oauthtoken {token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"zoho rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(
            ok=True, message=f"authenticated on datacenter {datacenter}",
        )


TYPE = ZohoCrmOAuth2Credential
