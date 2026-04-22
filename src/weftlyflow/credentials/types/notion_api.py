"""Notion API credential — integration token + ``Notion-Version`` header.

The Notion REST API (https://developers.notion.com/reference/intro)
authenticates every call with ``Authorization: Bearer secret_...`` and
additionally requires a ``Notion-Version`` header naming a supported API
revision. Getting that second header right is load-bearing — Notion will
reject requests with a missing or unknown version — so the credential
type bakes the default in and lets advanced users pin a different date.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_USERS_ME_URL: str = "https://api.notion.com/v1/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0
_DEFAULT_NOTION_VERSION: str = "2022-06-28"


class NotionApiCredential(BaseCredentialType):
    """Inject a Notion integration token + the required API-version header."""

    slug: ClassVar[str] = "weftlyflow.notion_api"
    display_name: ClassVar[str] = "Notion API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.notion.com/docs/authorization"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Integration Token",
            type="string",
            required=True,
            description="Notion integration secret (starts with 'secret_').",
            type_options={"password": True},
        ),
        PropertySchema(
            name="notion_version",
            display_name="API Version",
            type="string",
            default=_DEFAULT_NOTION_VERSION,
            required=False,
            description="Value for the required 'Notion-Version' header.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set the bearer token plus ``Notion-Version`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        version = str(creds.get("notion_version") or _DEFAULT_NOTION_VERSION).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["Notion-Version"] = version or _DEFAULT_NOTION_VERSION
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v1/users/me`` and report the outcome."""
        token = str(creds.get("access_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        version = str(creds.get("notion_version") or _DEFAULT_NOTION_VERSION).strip()
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _USERS_ME_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Notion-Version": version or _DEFAULT_NOTION_VERSION,
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"notion rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = NotionApiCredential
