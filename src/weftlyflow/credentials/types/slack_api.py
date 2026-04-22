"""Slack API credential — Bot/User token injected as an ``Authorization`` header.

Slack's Web API (https://api.slack.com/web) authenticates every request via
``Authorization: Bearer xoxb-...`` (bot tokens) or ``xoxp-...`` (user tokens).
The :class:`SlackApiCredential` type captures the access token plus an optional
``default_channel`` the Slack node uses when the operation parameter is blank.

The self-test calls ``auth.test`` — Slack's free verification endpoint — which
echoes the team + user identity when the token is valid.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_AUTH_TEST_URL: str = "https://slack.com/api/auth.test"
_TEST_TIMEOUT_SECONDS: float = 10.0


class SlackApiCredential(BaseCredentialType):
    """Inject a Slack Web API access token into the ``Authorization`` header."""

    slug: ClassVar[str] = "weftlyflow.slack_api"
    display_name: ClassVar[str] = "Slack API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://api.slack.com/authentication/token-types"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Slack bot (xoxb-...) or user (xoxp-...) token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="default_channel",
            display_name="Default Channel",
            type="string",
            required=False,
            description="Optional channel id or name used when a Slack node leaves it blank.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <access_token>`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``auth.test`` and report the outcome."""
        token = str(creds.get("access_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
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


TYPE = SlackApiCredential
