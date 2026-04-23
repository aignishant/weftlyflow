"""Salesforce REST credential — Bearer access token paired with a per-org ``instance_url``.

Salesforce (https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/
api_rest/) authenticates every REST call with ``Authorization: Bearer
<access_token>``, but the base URL varies *per org* — each production,
sandbox, or scratch-org lives at its own ``https://<myDomain>.my.salesforce.com``
host returned by the OAuth token exchange. That per-org URL is itself
sensitive (it leaks org identity) so this credential carries *both*
the token and the instance URL together as a tuple — a shape distinct
from plain Bearer / fixed-host credentials.

The self-test calls ``GET /services/oauth2/userinfo`` which accepts
any valid access token and echoes the user + org identifiers.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_USERINFO_PATH: str = "/services/oauth2/userinfo"
_TEST_TIMEOUT_SECONDS: float = 10.0


def instance_url_from(raw: str) -> str:
    """Normalize ``raw`` to ``<scheme>://<host>`` without trailing slash."""
    cleaned = raw.strip().rstrip("/")
    if not cleaned:
        msg = "Salesforce: 'instance_url' is required"
        raise ValueError(msg)
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    return cleaned


class SalesforceApiCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer <access_token>`` for a per-org host."""

    slug: ClassVar[str] = "weftlyflow.salesforce_api"
    display_name: ClassVar[str] = "Salesforce API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Salesforce OAuth2 access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="instance_url",
            display_name="Instance URL",
            type="string",
            required=True,
            description="Per-org base URL, e.g. 'https://myco.my.salesforce.com'.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <access_token>`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /services/oauth2/userinfo`` and report."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        try:
            base = instance_url_from(str(creds.get("instance_url") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_USERINFO_PATH}",
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
                message=f"salesforce rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = SalesforceApiCredential
