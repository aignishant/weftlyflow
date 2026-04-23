"""Zoom API credential — Server-to-Server OAuth Bearer token.

Zoom (https://developers.zoom.us/docs/api/) now uses Server-to-Server
OAuth: the calling service exchanges a long-lived account secret for a
short-lived access token and presents it as ``Authorization: Bearer
<access_token>``. Unlike plain Bearer credentials, Zoom *pairs* the
token with an ``account_id`` so operators can audit the originating
account from the credential record alone — the node never reads
``account_id`` on the wire, but surfacing it in the credential keeps
the operator contract complete.

The self-test calls ``GET /users/me``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_URL: str = "https://api.zoom.us/v2/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


class ZoomApiCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer <access_token>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.zoom_api"
    display_name: ClassVar[str] = "Zoom API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://developers.zoom.us/docs/api/"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Zoom Server-to-Server OAuth access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="account_id",
            display_name="Account ID",
            type="string",
            required=True,
            description="Zoom account ID the token was issued for (audit only).",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <access_token>``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /users/me`` and report."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        account_id = str(creds.get("account_id") or "").strip()
        if not account_id:
            return CredentialTestResult(ok=False, message="account_id is empty")
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
                message=f"zoom rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = ZoomApiCredential
