"""Mailchimp API credential — Basic auth with datacenter parsed from key.

Mailchimp's Marketing API v3
(https://mailchimp.com/developer/marketing/api/) authenticates via HTTP
Basic using any string as the username and the API key as the password.
The key itself carries the datacenter suffix (``abc-us6``) which
dictates the host: ``us6.api.mailchimp.com``. :meth:`datacenter_for`
extracts that suffix; the node layer uses it to compose the per-tenant
base URL.

The self-test calls ``GET /ping`` which returns ``"Everything's Chimpy!"``
for valid keys.
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_PATH: str = "/3.0/ping"
_TEST_TIMEOUT_SECONDS: float = 10.0
_PLACEHOLDER_USER: str = "weftlyflow"


def datacenter_for(api_key: str) -> str:
    """Return the ``usX`` datacenter segment encoded in ``api_key``."""
    stripped = api_key.strip()
    if "-" not in stripped:
        msg = "Mailchimp: api_key is missing the datacenter suffix (expected 'abc-us6')"
        raise ValueError(msg)
    suffix = stripped.rsplit("-", 1)[1]
    if not suffix:
        msg = "Mailchimp: api_key datacenter suffix is empty"
        raise ValueError(msg)
    return suffix


class MailchimpApiCredential(BaseCredentialType):
    """Inject Basic auth keyed by the Mailchimp API key."""

    slug: ClassVar[str] = "weftlyflow.mailchimp_api"
    display_name: ClassVar[str] = "Mailchimp API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://mailchimp.com/developer/marketing/guides/quick-start/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Marketing API key — ends with '-<datacenter>' (e.g. '-us6').",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Basic <base64(any:api_key)>`` on ``request``."""
        key = str(creds.get("api_key", "")).strip()
        encoded = base64.b64encode(
            f"{_PLACEHOLDER_USER}:{key}".encode(),
        ).decode("ascii")
        request.headers["Authorization"] = f"Basic {encoded}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /3.0/ping`` on the datacenter host and report."""
        key = str(creds.get("api_key") or "").strip()
        if not key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            datacenter = datacenter_for(key)
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        encoded = base64.b64encode(
            f"{_PLACEHOLDER_USER}:{key}".encode(),
        ).decode("ascii")
        url = f"https://{datacenter}.api.mailchimp.com{_TEST_PATH}"
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
                message=f"mailchimp rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(
            ok=True, message=f"authenticated on datacenter {datacenter}",
        )


TYPE = MailchimpApiCredential
