"""GitLab personal-access-token credential — ``PRIVATE-TOKEN`` header.

GitLab's REST API (https://docs.gitlab.com/ee/api/rest/) accepts a
personal-access token (or project/group access token) as a plain
``PRIVATE-TOKEN`` header — no ``Bearer`` prefix. The node layer can
target either gitlab.com or a self-hosted instance, so the base URL is
part of the credential.

The self-test calls ``GET /api/v4/user`` which every valid token can
read.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEFAULT_BASE_URL: str = "https://gitlab.com"
_TEST_PATH: str = "/api/v4/user"
_TEST_TIMEOUT_SECONDS: float = 10.0


class GitLabTokenCredential(BaseCredentialType):
    """Inject ``PRIVATE-TOKEN: <access_token>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.gitlab_token"
    display_name: ClassVar[str] = "GitLab Access Token"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            default=_DEFAULT_BASE_URL,
            description="GitLab instance base URL (no trailing slash).",
            placeholder=_DEFAULT_BASE_URL,
        ),
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Personal, group, or project access token.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``PRIVATE-TOKEN: <access_token>`` on ``request``."""
        token = str(creds.get("access_token", "")).strip()
        request.headers["PRIVATE-TOKEN"] = token
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v4/user`` and report the outcome."""
        raw_base = str(creds.get("base_url") or _DEFAULT_BASE_URL).strip().rstrip("/")
        base_url = raw_base or _DEFAULT_BASE_URL
        token = str(creds.get("access_token", "")).strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base_url}{_TEST_PATH}",
                    headers={"PRIVATE-TOKEN": token},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"gitlab rejected token: HTTP {response.status_code}",
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


TYPE = GitLabTokenCredential
