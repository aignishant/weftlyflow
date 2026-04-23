"""Bitbucket Cloud credential — Basic auth (username + app password) + workspace.

Bitbucket Cloud (https://support.atlassian.com/bitbucket-cloud/docs/
app-passwords/) authenticates with HTTP Basic using the account
``username`` and a scoped **app password** (NOT the account password —
Atlassian has fully sunset password basic-auth). What makes the
credential distinctive is the mandatory ``workspace`` slug that is
embedded into every URL path: ``/2.0/repositories/{workspace}/...``,
``/2.0/workspaces/{workspace}/...``, etc. The credential carries the
default workspace so node calls do not need to repeat it.

This is the first credential to *path-scope* via a workspace slug
(distinct from path-scoping by realmId in QuickBooks, which routes to
``/v3/company/{realmId}``).

The self-test calls ``GET /2.0/user`` which returns the authenticated
user's profile on valid credentials.
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: Final[str] = "https://api.bitbucket.org"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def _basic_header(username: str, app_password: str) -> str:
    """Return ``Basic <base64(username:app_password)>``."""
    raw = f"{username}:{app_password}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


class BitbucketApiCredential(BaseCredentialType):
    """Inject Basic auth — workspace slug is consumed by the node."""

    slug: ClassVar[str] = "weftlyflow.bitbucket_api"
    display_name: ClassVar[str] = "Bitbucket Cloud"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://support.atlassian.com/bitbucket-cloud/docs/app-passwords/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="username",
            display_name="Username",
            type="string",
            required=True,
            description="Bitbucket account username (NOT email).",
        ),
        PropertySchema(
            name="app_password",
            display_name="App Password",
            type="string",
            required=True,
            description="Scoped app password (NOT the account password).",
            type_options={"password": True},
        ),
        PropertySchema(
            name="workspace",
            display_name="Workspace",
            type="string",
            required=True,
            description="Default workspace slug — embedded in every URL path.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Basic <b64(username:app_password)>``."""
        username = str(creds.get("username", "")).strip()
        app_password = str(creds.get("app_password", "")).strip()
        request.headers["Authorization"] = _basic_header(username, app_password)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /2.0/user`` and report the outcome."""
        username = str(creds.get("username") or "").strip()
        app_password = str(creds.get("app_password") or "").strip()
        if not username or not app_password:
            return CredentialTestResult(
                ok=False,
                message="username and app_password are required",
            )
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}/2.0/user",
                    headers={
                        "Authorization": _basic_header(username, app_password),
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"bitbucket rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = BitbucketApiCredential
