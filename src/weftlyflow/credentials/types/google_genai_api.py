"""Google Generative Language API credential — ``x-goog-api-key`` header.

Google's Generative Language API
(https://ai.google.dev/api/rest) authenticates with a simple
``x-goog-api-key: <key>`` header. Unlike the OAuth2-based Gmail /
Drive / Sheets credentials, this is a plain API-key auth intended
for calling Gemini models directly — no refresh flow, no scopes.
The API also accepts ``?key=<key>`` as a query-string fallback, but
the header form keeps the key out of access logs on the forward
path so the injector only installs the header.

Self-test: ``GET /v1beta/models`` returns 200 + a page of models on
a valid key, 403 ``PERMISSION_DENIED`` otherwise.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: Final[str] = "https://generativelanguage.googleapis.com"
_API_KEY_HEADER: Final[str] = "x-goog-api-key"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class GoogleGenAIApiCredential(BaseCredentialType):
    """Inject the ``x-goog-api-key`` header for Gemini API calls."""

    slug: ClassVar[str] = "weftlyflow.google_genai_api"
    display_name: ClassVar[str] = "Google GenAI API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = "https://ai.google.dev/api/rest"
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Gemini API key from Google AI Studio.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set the ``x-goog-api-key`` header on outgoing requests."""
        api_key = str(creds.get("api_key", "")).strip()
        request.headers[_API_KEY_HEADER] = api_key
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v1beta/models`` and report the outcome."""
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}/v1beta/models",
                    headers={
                        _API_KEY_HEADER: api_key,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"google rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = GoogleGenAIApiCredential
