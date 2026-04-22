"""HTTP Basic-auth credential — ``Authorization: Basic base64(user:password)``."""

from __future__ import annotations

import base64
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema


class BasicAuthCredential(BaseCredentialType):
    """Inject RFC 7617 basic-auth credentials."""

    slug: ClassVar[str] = "weftlyflow.basic_auth"
    display_name: ClassVar[str] = "Basic Auth"
    generic: ClassVar[bool] = True
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="username",
            display_name="Username",
            type="string",
            required=True,
        ),
        PropertySchema(
            name="password",
            display_name="Password",
            type="string",
            required=True,
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Basic <b64>`` on ``request``."""
        username = str(creds.get("username", ""))
        password = str(creds.get("password", ""))
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        request.headers["Authorization"] = f"Basic {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Report whether both fields are populated."""
        if not creds.get("username") or not creds.get("password"):
            return CredentialTestResult(ok=False, message="username and password required")
        return CredentialTestResult(ok=True)


TYPE = BasicAuthCredential
