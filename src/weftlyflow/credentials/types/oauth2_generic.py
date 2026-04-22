"""Generic OAuth2 credential — Authorization Code + Client Credentials flows.

The credential stores ``access_token``, ``refresh_token``, ``expires_at``,
plus provider URLs. Token refresh is handled by a Celery task that writes
the new token back to the credential row; injection here is a simple
``Authorization: Bearer <access_token>`` just like :class:`BearerToken`.

Provider-specific subclasses (e.g. ``slack_oauth2``) can subclass and set
``authorization_url`` / ``token_url`` / ``scope`` as class defaults.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema


class OAuth2GenericCredential(BaseCredentialType):
    """Generic OAuth2 credential — inject ``Authorization: Bearer <access_token>``."""

    slug: ClassVar[str] = "weftlyflow.oauth2_generic"
    display_name: ClassVar[str] = "OAuth2 (Generic)"
    generic: ClassVar[bool] = True
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="authorization_url",
            display_name="Authorization URL",
            type="string",
            required=True,
        ),
        PropertySchema(
            name="token_url",
            display_name="Token URL",
            type="string",
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
            default="",
            required=False,
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

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <access_token>``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Confirm at minimum that an access token is present."""
        if not str(creds.get("access_token", "")).strip():
            return CredentialTestResult(
                ok=False,
                message="no access_token — complete the OAuth flow first",
            )
        return CredentialTestResult(ok=True)


TYPE = OAuth2GenericCredential
