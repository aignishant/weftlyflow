"""Jira Cloud credential — email + API token via HTTP Basic auth.

Atlassian Cloud's REST API (https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
authenticates with the user's email as HTTP Basic username and an API
token (generated at https://id.atlassian.com/manage-profile/security/api-tokens)
as the password. Every tenant lives at its own
``https://<site>.atlassian.net`` host, so the site is stored on the
credential and used by the node to build the base URL.

The self-test calls ``GET /rest/api/3/myself`` against the configured
site and reports the authenticated user.
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_PATH: str = "/rest/api/3/myself"
_TEST_TIMEOUT_SECONDS: float = 10.0


class JiraCloudCredential(BaseCredentialType):
    """Inject ``Authorization: Basic base64(email:api_token)`` per request."""

    slug: ClassVar[str] = "weftlyflow.jira_cloud"
    display_name: ClassVar[str] = "Jira Cloud"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="site",
            display_name="Site",
            type="string",
            required=True,
            description="Atlassian site slug — '<site>.atlassian.net'.",
            placeholder="your-team",
        ),
        PropertySchema(
            name="email",
            display_name="Email",
            type="string",
            required=True,
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
        """Set ``Authorization: Basic <b64(email:token)>`` on ``request``."""
        email = str(creds.get("email", ""))
        token = str(creds.get("api_token", ""))
        encoded = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
        request.headers["Authorization"] = f"Basic {encoded}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /rest/api/3/myself`` against the configured site."""
        site = str(creds.get("site", "")).strip()
        email = str(creds.get("email", "")).strip()
        token = str(creds.get("api_token", "")).strip()
        if not site or not email or not token:
            return CredentialTestResult(
                ok=False,
                message="site, email, and api_token are required",
            )
        url = f"https://{site}.atlassian.net{_TEST_PATH}"
        encoded = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": f"Basic {encoded}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"jira rejected credentials: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        display_name = ""
        if isinstance(payload, dict):
            display_name = str(payload.get("displayName", ""))
        suffix = f" as {display_name}" if display_name else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = JiraCloudCredential
