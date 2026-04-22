"""Trello API credential — key + token as query parameters.

Trello's REST API (https://developer.atlassian.com/cloud/trello/rest/) takes
both an API **key** (identifies the app) and an API **token** (identifies
the user) as query-string parameters on every request. :meth:`inject`
appends ``key=<k>&token=<t>`` onto ``request.url``.

The self-test calls ``GET /1/members/me`` which returns the authenticated
user's profile.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_MEMBERS_ME_URL: str = "https://api.trello.com/1/members/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


class TrelloApiCredential(BaseCredentialType):
    """Append ``key=<k>&token=<t>`` to every outbound Trello URL."""

    slug: ClassVar[str] = "weftlyflow.trello_api"
    display_name: ClassVar[str] = "Trello API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            type_options={"password": True},
        ),
        PropertySchema(
            name="api_token",
            display_name="API Token",
            type="string",
            required=True,
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Append ``key`` + ``token`` query parameters to ``request.url``."""
        key = str(creds.get("api_key", "")).strip()
        token = str(creds.get("api_token", "")).strip()
        request.url = request.url.copy_merge_params({"key": key, "token": token})
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /1/members/me`` and report the outcome."""
        key = str(creds.get("api_key", "")).strip()
        token = str(creds.get("api_token", "")).strip()
        if not key or not token:
            return CredentialTestResult(ok=False, message="api_key and api_token are required")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _MEMBERS_ME_URL, params={"key": key, "token": token},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"trello rejected credentials: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        username = ""
        if isinstance(payload, dict):
            username = str(payload.get("username", ""))
        suffix = f" as {username}" if username else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = TrelloApiCredential
