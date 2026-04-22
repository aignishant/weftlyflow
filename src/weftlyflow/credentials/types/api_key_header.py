"""API-key-as-header credential — e.g. ``X-API-Key: ...``."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema


class ApiKeyHeaderCredential(BaseCredentialType):
    """Inject an API key under an arbitrary header name."""

    slug: ClassVar[str] = "weftlyflow.api_key_header"
    display_name: ClassVar[str] = "API Key (Header)"
    generic: ClassVar[bool] = True
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="header_name",
            display_name="Header name",
            type="string",
            default="X-API-Key",
            required=True,
        ),
        PropertySchema(
            name="api_key",
            display_name="API key",
            type="string",
            required=True,
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``<header_name>: <api_key>`` on ``request``."""
        header = str(creds.get("header_name", "X-API-Key")).strip() or "X-API-Key"
        request.headers[header] = str(creds.get("api_key", ""))
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Check that both fields are non-empty."""
        if not creds.get("header_name") or not creds.get("api_key"):
            return CredentialTestResult(ok=False, message="header_name and api_key required")
        return CredentialTestResult(ok=True)


TYPE = ApiKeyHeaderCredential
