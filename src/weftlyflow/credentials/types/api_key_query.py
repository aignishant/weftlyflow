"""API-key-as-query-parameter credential — e.g. ``?api_key=...``."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema


class ApiKeyQueryCredential(BaseCredentialType):
    """Append the API key to the outgoing URL's query string."""

    slug: ClassVar[str] = "weftlyflow.api_key_query"
    display_name: ClassVar[str] = "API Key (Query)"
    generic: ClassVar[bool] = True
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="param_name",
            display_name="Query parameter name",
            type="string",
            default="api_key",
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
        """Append ``?param_name=api_key`` to the request URL."""
        name = str(creds.get("param_name", "api_key")).strip() or "api_key"
        value = str(creds.get("api_key", ""))
        params = dict(request.url.params)
        params[name] = value
        request.url = request.url.copy_with(params=params)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Confirm both fields are populated."""
        if not creds.get("param_name") or not creds.get("api_key"):
            return CredentialTestResult(ok=False, message="param_name and api_key required")
        return CredentialTestResult(ok=True)


TYPE = ApiKeyQueryCredential
