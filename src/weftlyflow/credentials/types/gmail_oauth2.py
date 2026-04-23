"""Gmail OAuth2 credential — Google OAuth2 pre-filled for the Gmail API.

Identical wire contract to :class:`OAuth2GenericCredential` — the access
token is injected as ``Authorization: Bearer <token>`` — but the
property defaults are narrowed to Google's OAuth2 endpoints and the
Gmail **send** scope so credential setup in the UI is a one-click
affair.

Reference: https://developers.google.com/gmail/api/auth/scopes.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import CredentialTestResult
from weftlyflow.credentials.types.oauth2_generic import OAuth2GenericCredential
from weftlyflow.domain.node_spec import PropertySchema

_TOKENINFO_URL: str = "https://oauth2.googleapis.com/tokeninfo"
_TEST_TIMEOUT_SECONDS: float = 10.0
_DEFAULT_AUTHORIZATION_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
_DEFAULT_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
_DEFAULT_SCOPE: str = "https://www.googleapis.com/auth/gmail.send"


class GmailOAuth2Credential(OAuth2GenericCredential):
    """Google-flavoured OAuth2 credential scoped for the Gmail API."""

    slug: ClassVar[str] = "weftlyflow.gmail_oauth2"
    display_name: ClassVar[str] = "Gmail OAuth2"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.google.com/gmail/api/auth/about-auth"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="authorization_url",
            display_name="Authorization URL",
            type="string",
            default=_DEFAULT_AUTHORIZATION_URL,
            required=True,
        ),
        PropertySchema(
            name="token_url",
            display_name="Token URL",
            type="string",
            default=_DEFAULT_TOKEN_URL,
            required=True,
        ),
        PropertySchema(
            name="client_id",
            display_name="Client ID",
            type="string",
            required=True,
        ),
        PropertySchema(
            name="client_secret",
            display_name="Client Secret",
            type="string",
            required=True,
            type_options={"password": True},
        ),
        PropertySchema(
            name="scope",
            display_name="Scope",
            type="string",
            default=_DEFAULT_SCOPE,
            required=False,
            description="Space-separated Gmail API scopes.",
        ),
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            default="",
            required=False,
            type_options={"password": True},
        ),
        PropertySchema(
            name="refresh_token",
            display_name="Refresh Token",
            type="string",
            default="",
            required=False,
            type_options={"password": True},
        ),
        PropertySchema(
            name="expires_at",
            display_name="Access token expiry (epoch seconds)",
            type="number",
            default=0,
            required=False,
        ),
    ]

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Validate the access token via Google's ``tokeninfo`` endpoint."""
        token = str(creds.get("access_token", "")).strip()
        if not token:
            return CredentialTestResult(
                ok=False,
                message="no access_token — complete the OAuth flow first",
            )
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _TOKENINFO_URL, params={"access_token": token},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"google rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="token valid")


TYPE = GmailOAuth2Credential
