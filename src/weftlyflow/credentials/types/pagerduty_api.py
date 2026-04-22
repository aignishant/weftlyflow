"""PagerDuty API credential — ``Authorization: Token token=<key>`` header.

PagerDuty's REST API v2 (https://developer.pagerduty.com/api-reference/)
uses a distinctive ``Token token=<api_key>`` auth header rather than
plain ``Bearer``. An admin email (``from_email``) must accompany every
mutating request via the ``From`` header; the node layer forwards it
when the credential supplies one.

The self-test calls ``GET /users/me`` which echoes the authenticated
user's profile.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: str = "https://api.pagerduty.com"
_TEST_PATH: str = "/users/me"
_TEST_TIMEOUT_SECONDS: float = 10.0


class PagerDutyApiCredential(BaseCredentialType):
    """Inject ``Authorization: Token token=<api_key>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.pagerduty_api"
    display_name: ClassVar[str] = "PagerDuty API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.pagerduty.com/docs/rest-api-authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="PagerDuty REST API key (user or general).",
            type_options={"password": True},
        ),
        PropertySchema(
            name="from_email",
            display_name="From Email",
            type="string",
            description=(
                "Admin email sent in the 'From' header on mutating requests."
            ),
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Token token=<api_key>`` on ``request``."""
        key = str(creds.get("api_key", "")).strip()
        request.headers["Authorization"] = f"Token token={key}"
        from_email = str(creds.get("from_email", "")).strip()
        if from_email:
            request.headers.setdefault("From", from_email)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /users/me`` and report the outcome."""
        key = str(creds.get("api_key", "")).strip()
        if not key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}{_TEST_PATH}",
                    headers={
                        "Authorization": f"Token token={key}",
                        "Accept": "application/vnd.pagerduty+json;version=2",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"pagerduty rejected key: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        name = ""
        if isinstance(payload, dict):
            user = payload.get("user")
            if isinstance(user, dict):
                name = str(user.get("name", "") or user.get("email", ""))
        suffix = f" as {name}" if name else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = PagerDutyApiCredential
