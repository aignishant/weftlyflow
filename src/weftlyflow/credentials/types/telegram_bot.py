"""Telegram bot credential — token embedded in the request path.

Telegram's Bot API (https://core.telegram.org/bots/api) authenticates by
placing the bot token directly in the URL:
``https://api.telegram.org/bot<TOKEN>/sendMessage``. There is **no**
``Authorization`` header, so :meth:`inject` is a no-op. The node reads
``bot_token`` from the resolved payload and composes the URL itself.

The self-test calls ``GET /bot{TOKEN}/getMe`` which any valid token can
answer.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE: str = "https://api.telegram.org"
_TEST_TIMEOUT_SECONDS: float = 10.0


class TelegramBotCredential(BaseCredentialType):
    """Hold a Telegram bot token; URL-embedded at call time (no header)."""

    slug: ClassVar[str] = "weftlyflow.telegram_bot"
    display_name: ClassVar[str] = "Telegram Bot"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://core.telegram.org/bots#how-do-i-create-a-bot"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="bot_token",
            display_name="Bot Token",
            type="string",
            required=True,
            description="Token issued by @BotFather — '123456:ABC-...'.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """No-op — Telegram authenticates via the URL, not headers."""
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /bot<token>/getMe`` and report the outcome."""
        token = str(creds.get("bot_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="bot_token is empty")
        url = f"{_API_BASE}/bot{token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"telegram rejected token: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        result = payload.get("result") if isinstance(payload, dict) else None
        username = ""
        if isinstance(result, dict):
            username = str(result.get("username", ""))
        suffix = f" as @{username}" if username else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = TelegramBotCredential
