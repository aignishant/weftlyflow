"""Slack OAuth2 credential — Authorization Code flow for the Slack app install.

Slack's ``oauth.v2.access`` returns a bot token (``xoxb-...``) after the user
approves the app. Once the flow completes, the credential row stores the
access token alongside the standard OAuth2 fields; injection is identical to
:class:`~weftlyflow.credentials.types.oauth2_generic.OAuth2GenericCredential`
— ``Authorization: Bearer <access_token>``.

The difference from the generic OAuth2 type is the defaults: Slack's
authorization + token URLs and the scope list most Slack apps request. The
self-test reuses Slack's free ``auth.test`` endpoint, matching
:class:`~weftlyflow.credentials.types.slack_api.SlackApiCredential`.

See https://api.slack.com/authentication/oauth-v2 for the protocol.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import CredentialTestResult
from weftlyflow.credentials.types.oauth2_generic import OAuth2GenericCredential
from weftlyflow.domain.node_spec import PropertySchema

_AUTH_TEST_URL: str = "https://slack.com/api/auth.test"
_TEST_TIMEOUT_SECONDS: float = 10.0
_DEFAULT_AUTHORIZATION_URL: str = "https://slack.com/oauth/v2/authorize"
_DEFAULT_TOKEN_URL: str = "https://slack.com/api/oauth.v2.access"
_DEFAULT_SCOPE: str = "chat:write,channels:read,groups:read"


class SlackOAuth2Credential(OAuth2GenericCredential):
    """Slack-flavoured OAuth2 credential with pre-filled endpoints."""

    slug: ClassVar[str] = "weftlyflow.slack_oauth2"
    display_name: ClassVar[str] = "Slack OAuth2"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://api.slack.com/authentication/oauth-v2"
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
            description="Comma-separated bot scopes — see https://api.slack.com/scopes.",
        ),
        PropertySchema(
            name="default_channel",
            display_name="Default Channel",
            type="string",
            required=False,
            description="Optional channel id or name used when a Slack node leaves it blank.",
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
        """Call Slack's ``auth.test`` with the stored token."""
        token = str(creds.get("access_token", "")).strip()
        if not token:
            return CredentialTestResult(
                ok=False,
                message="no access_token — complete the OAuth flow first",
            )
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    _AUTH_TEST_URL,
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        payload: Any
        try:
            payload = response.json()
        except ValueError:
            return CredentialTestResult(ok=False, message="non-JSON response from Slack")
        if not isinstance(payload, dict) or not payload.get("ok"):
            error = str(payload.get("error") if isinstance(payload, dict) else "unknown_error")
            return CredentialTestResult(ok=False, message=f"slack rejected token: {error}")
        team = str(payload.get("team", ""))
        user = str(payload.get("user", ""))
        return CredentialTestResult(ok=True, message=f"authenticated as {user}@{team}")


TYPE = SlackOAuth2Credential
