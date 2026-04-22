"""Bearer-token credential — ``Authorization: Bearer <token>``."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema


class BearerTokenCredential(BaseCredentialType):
    """Inject a bearer token into the ``Authorization`` header."""

    slug: ClassVar[str] = "weftlyflow.bearer_token"
    display_name: ClassVar[str] = "Bearer Token"
    generic: ClassVar[bool] = True
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="token",
            display_name="Token",
            type="string",
            required=True,
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <token>`` on a copy of ``request``."""
        token = str(creds.get("token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Report whether a token was supplied — network test is provider-specific."""
        if not str(creds.get("token", "")).strip():
            return CredentialTestResult(ok=False, message="token is empty")
        return CredentialTestResult(ok=True, message="token present")


TYPE = BearerTokenCredential
