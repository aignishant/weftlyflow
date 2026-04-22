"""Discord bot credential — ``Authorization: Bot <token>``.

Discord's REST API (https://discord.com/developers/docs/reference) uses a
custom ``Bot`` prefix in the ``Authorization`` header rather than the
industry-standard ``Bearer``. This credential type captures just the bot
token and injects the correctly-prefixed header. The self-test calls
``GET /users/@me`` which any bot token can read.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_USERS_ME_URL: str = "https://discord.com/api/v10/users/@me"
_TEST_TIMEOUT_SECONDS: float = 10.0


class DiscordBotCredential(BaseCredentialType):
    """Inject ``Authorization: Bot <token>`` on every outbound request."""

    slug: ClassVar[str] = "weftlyflow.discord_bot"
    display_name: ClassVar[str] = "Discord Bot"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://discord.com/developers/docs/topics/oauth2#bot-authorization-flow"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="bot_token",
            display_name="Bot Token",
            type="string",
            required=True,
            description="The bot token from the Discord Developer Portal.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bot <bot_token>`` on ``request``."""
        token = str(creds.get("bot_token", "")).strip()
        request.headers["Authorization"] = f"Bot {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /users/@me`` and report the outcome."""
        token = str(creds.get("bot_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="bot_token is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _USERS_ME_URL, headers={"Authorization": f"Bot {token}"},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"discord rejected token: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        name = str(payload.get("username", "")) if isinstance(payload, dict) else ""
        suffix = f" as {name}" if name else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = DiscordBotCredential
