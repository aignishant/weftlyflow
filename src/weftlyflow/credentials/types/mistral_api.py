"""Mistral La Plateforme API credential — ``Authorization: Bearer <key>``.

Mistral's La Plateforme (https://docs.mistral.ai/) uses the standard
Bearer scheme — straightforward, in contrast with Anthropic's
``x-api-key`` or Google's ``x-goog-api-key`` header. The credential
stays dedicated rather than reusing the generic bearer type so that
the self-test can hit Mistral's own ``GET /v1/models`` endpoint and
because nodes bind to a specific credential slug, not a generic one.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: Final[str] = "https://api.mistral.ai"
_AUTH_HEADER: Final[str] = "Authorization"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class MistralApiCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer <api_key>`` for Mistral API calls."""

    slug: ClassVar[str] = "weftlyflow.mistral_api"
    display_name: ClassVar[str] = "Mistral API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.mistral.ai/getting-started/quickstart/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Mistral API key from La Plateforme console.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <api_key>`` on outgoing requests."""
        api_key = str(creds.get("api_key", "")).strip()
        request.headers[_AUTH_HEADER] = f"Bearer {api_key}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v1/models`` and report the outcome."""
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}/v1/models",
                    headers={
                        _AUTH_HEADER: f"Bearer {api_key}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"mistral rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = MistralApiCredential
