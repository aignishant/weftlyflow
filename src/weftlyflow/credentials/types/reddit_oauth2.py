"""Reddit OAuth2 credential — Bearer token + mandatory Reddit-specific User-Agent.

Reddit's API (https://www.reddit.com/dev/api/) accepts OAuth2 Bearer
tokens but additionally **enforces** a User-Agent header that follows
a platform-specific format:

``<platform>:<app-id>:<version> (by /u/<reddit-username>)``

Requests omitting the User-Agent — or using a generic default like
``python-httpx/0.27.0`` — are throttled or outright rejected with HTTP
429. This credential therefore stores the three User-Agent components
(platform, app_id, version, username) alongside the access token and
assembles the header on every :meth:`inject` call.

Bearer tokens are typically obtained via Reddit's *script-app* OAuth2
flow (user-less client credentials); this credential expects a
pre-exchanged ``access_token`` rather than client id/secret — keeping
the runtime shape simple and matching the pattern used by the catalog's
other pre-exchanged-Bearer credentials.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_WHOAMI_URL: str = "https://oauth.reddit.com/api/v1/me"
_DEFAULT_PLATFORM: str = "web"
_TEST_TIMEOUT_SECONDS: float = 10.0


class RedditOAuth2Credential(BaseCredentialType):
    """Inject Bearer token + Reddit-formatted User-Agent."""

    slug: ClassVar[str] = "weftlyflow.reddit_oauth2"
    display_name: ClassVar[str] = "Reddit OAuth2"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://www.reddit.com/dev/api/"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            type_options={"password": True},
            description="Pre-exchanged Reddit OAuth2 bearer token.",
        ),
        PropertySchema(
            name="platform",
            display_name="Platform",
            type="string",
            required=True,
            default=_DEFAULT_PLATFORM,
            description="User-Agent platform segment, e.g. 'web', 'desktop', 'linux'.",
        ),
        PropertySchema(
            name="app_id",
            display_name="App ID",
            type="string",
            required=True,
            description="Short, unique app identifier (User-Agent segment two).",
        ),
        PropertySchema(
            name="version",
            display_name="App Version",
            type="string",
            required=True,
            description="App version string, e.g. '1.0.0' (User-Agent segment three).",
        ),
        PropertySchema(
            name="username",
            display_name="Reddit Username",
            type="string",
            required=True,
            description="Reddit username used as the 'by /u/<name>' suffix.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer`` and a Reddit-formatted User-Agent."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["User-Agent"] = _build_user_agent(creds)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v1/me`` to verify both token and user-agent are accepted."""
        token = str(creds.get("access_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is required")
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": _build_user_agent(creds),
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
                message=f"reddit rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="reddit credentials valid")


def _build_user_agent(creds: dict[str, Any]) -> str:
    platform = str(creds.get("platform") or _DEFAULT_PLATFORM).strip() or _DEFAULT_PLATFORM
    app_id = str(creds.get("app_id") or "weftlyflow").strip() or "weftlyflow"
    version = str(creds.get("version") or "0.0.0").strip() or "0.0.0"
    username = str(creds.get("username") or "").strip()
    suffix = f" (by /u/{username})" if username else ""
    return f"{platform}:{app_id}:{version}{suffix}"


TYPE = RedditOAuth2Credential
