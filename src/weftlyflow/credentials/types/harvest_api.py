"""Harvest API credential — Bearer + mandatory ``Harvest-Account-ID`` header.

Harvest (https://help.getharvest.com/api-v2/) authenticates by Bearer
Personal Access Token, **and** requires a mandatory
``Harvest-Account-ID: <id>`` header that scopes the call to a specific
Harvest account — a single PAT can have access to several accounts.

This is the catalog's first **dual-header** credential where both a
bearer token and an account-scoping identifier header are required;
neither alone is sufficient. Harvest additionally requires a
``User-Agent`` that identifies the integration, which we set to a
stable Weftlyflow value.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_USER_AGENT: str = "Weftlyflow (+https://weftlyflow.dev)"
_WHOAMI_URL: str = "https://api.harvestapp.com/v2/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


class HarvestApiCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer`` + ``Harvest-Account-ID`` + ``User-Agent``."""

    slug: ClassVar[str] = "weftlyflow.harvest_api"
    display_name: ClassVar[str] = "Harvest API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://help.getharvest.com/api-v2/authentication-api/authentication/authentication/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Personal Access Token",
            type="string",
            required=True,
            type_options={"password": True},
            description="Harvest PAT or OAuth2 access token.",
        ),
        PropertySchema(
            name="account_id",
            display_name="Harvest Account ID",
            type="string",
            required=True,
            description="Numeric account ID — scopes every call to a specific Harvest account.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer token, Harvest-Account-ID, and User-Agent on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        account_id = str(creds.get("account_id", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["Harvest-Account-ID"] = account_id
        request.headers.setdefault("User-Agent", _USER_AGENT)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v2/users/me`` to verify both token and account scope."""
        token = str(creds.get("access_token", "")).strip()
        account_id = str(creds.get("account_id", "")).strip()
        if not token or not account_id:
            return CredentialTestResult(
                ok=False, message="access_token and account_id are required",
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Harvest-Account-ID": account_id,
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(_WHOAMI_URL, headers=headers)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"harvest rejected credentials: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        email = ""
        if isinstance(payload, dict):
            email = str(payload.get("email") or "")
        suffix = f" as {email}" if email else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = HarvestApiCredential
