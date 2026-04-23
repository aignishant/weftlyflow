"""Box credential — Bearer OAuth2 token + optional ``As-User`` impersonation.

Box (https://developer.box.com/reference/) accepts a short-lived
OAuth2 access token via ``Authorization: Bearer <access_token>``. The
distinctive shape is the optional ``As-User: <user_id>`` header that
enterprise admins and JWT-service-account apps use to impersonate a
managed user for the duration of a single request. Carrying the
impersonation target on the credential keeps the scope stable across
workflow steps that re-auth the same account.

The self-test calls ``GET /2.0/users/me``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_URL: str = "https://api.box.com/2.0/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0
_AS_USER_HEADER: str = "As-User"


class BoxApiCredential(BaseCredentialType):
    """Inject Bearer token and optional ``As-User`` impersonation header."""

    slug: ClassVar[str] = "weftlyflow.box_api"
    display_name: ClassVar[str] = "Box API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://developer.box.com/reference/"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="OAuth2 or JWT-server-auth access token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="as_user_id",
            display_name="Act As User ID",
            type="string",
            required=False,
            description=(
                "Enterprise user ID to impersonate — sent as the "
                "'As-User' header. Leave blank to act as the token owner."
            ),
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer auth and optional ``As-User`` header."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        as_user = str(creds.get("as_user_id") or "").strip()
        if as_user:
            request.headers[_AS_USER_HEADER] = as_user
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /2.0/users/me`` and report the outcome."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        as_user = str(creds.get("as_user_id") or "").strip()
        if as_user:
            headers[_AS_USER_HEADER] = as_user
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(_TEST_URL, headers=headers)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"box rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = BoxApiCredential
