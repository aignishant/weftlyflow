"""Okta API credential — ``Authorization: SSWS <token>`` custom scheme.

Okta (https://developer.okta.com/docs/reference/core-okta-api/) ships
its own authorization scheme: the header literally reads
``Authorization: SSWS <token>`` — not ``Bearer``, not ``Basic``, not
any OAuth-style prefix. Every tenant gets a per-org URL
(``https://<org>.okta.com``), so the credential carries both the token
and the org URL.

The self-test calls ``GET /api/v1/users/me`` which echoes the
authenticated user.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_VERSION_PREFIX: str = "/api/v1"
_TEST_PATH: str = "/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


def base_url_from(raw_org_url: str) -> str:
    """Normalize ``raw_org_url`` to ``https://<host>/api/v1``."""
    cleaned = raw_org_url.strip().rstrip("/")
    if not cleaned:
        msg = "Okta: 'org_url' is required"
        raise ValueError(msg)
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    return f"{cleaned}{_API_VERSION_PREFIX}"


def ssws_header(token: str) -> str:
    """Return the ``Authorization`` header value for ``token``."""
    return f"SSWS {token}"


class OktaApiCredential(BaseCredentialType):
    """Inject ``Authorization: SSWS <api_token>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.okta_api"
    display_name: ClassVar[str] = "Okta API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.okta.com/docs/reference/core-okta-api/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_token",
            display_name="API Token",
            type="string",
            required=True,
            description="Okta API token from the admin console.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="org_url",
            display_name="Org URL",
            type="string",
            required=True,
            description="Org base URL, e.g. 'https://acme.okta.com'.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: SSWS <api_token>`` on ``request``."""
        token = str(creds.get("api_token", "")).strip()
        request.headers["Authorization"] = ssws_header(token)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v1/users/me`` on the tenant host and report."""
        token = str(creds.get("api_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="api_token is empty")
        try:
            base = base_url_from(str(creds.get("org_url") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_TEST_PATH}",
                    headers={
                        "Authorization": ssws_header(token),
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"okta rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = OktaApiCredential
