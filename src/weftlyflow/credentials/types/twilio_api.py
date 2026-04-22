"""Twilio API credential — Account SID + Auth Token via HTTP Basic auth.

Twilio's REST API (https://www.twilio.com/docs/usage/api) authenticates
with the project Account SID as HTTP Basic username and the Auth Token
(from the Twilio console) as the password. The Account SID also appears
as a path segment on every resource (``/Accounts/{AccountSid}/...``), so
it lives on the credential — the node layer reads it when building
paths.

The self-test calls ``GET /2010-04-01/Accounts/{AccountSid}.json`` which
every valid Auth Token can read.
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: str = "https://api.twilio.com"
_TEST_TIMEOUT_SECONDS: float = 10.0


class TwilioApiCredential(BaseCredentialType):
    """Inject ``Authorization: Basic base64(sid:auth_token)`` per request."""

    slug: ClassVar[str] = "weftlyflow.twilio_api"
    display_name: ClassVar[str] = "Twilio API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://www.twilio.com/docs/iam/api-keys"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="account_sid",
            display_name="Account SID",
            type="string",
            required=True,
            description="Twilio Account SID (starts with 'AC').",
            placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        ),
        PropertySchema(
            name="auth_token",
            display_name="Auth Token",
            type="string",
            required=True,
            description="Twilio Auth Token from the console.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Basic <b64(sid:token)>`` on ``request``."""
        sid = str(creds.get("account_sid", "")).strip()
        token = str(creds.get("auth_token", "")).strip()
        encoded = base64.b64encode(f"{sid}:{token}".encode()).decode("ascii")
        request.headers["Authorization"] = f"Basic {encoded}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /2010-04-01/Accounts/{AccountSid}.json`` and report."""
        sid = str(creds.get("account_sid", "")).strip()
        token = str(creds.get("auth_token", "")).strip()
        if not sid or not token:
            return CredentialTestResult(
                ok=False,
                message="account_sid and auth_token are required",
            )
        url = f"{_API_BASE_URL}/2010-04-01/Accounts/{sid}.json"
        encoded = base64.b64encode(f"{sid}:{token}".encode()).decode("ascii")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url, headers={"Authorization": f"Basic {encoded}"},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"twilio rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = TwilioApiCredential
