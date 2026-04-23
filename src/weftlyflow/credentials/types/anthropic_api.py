"""Anthropic API credential — ``x-api-key`` + mandatory ``anthropic-version`` header.

Anthropic (https://docs.anthropic.com/en/api/getting-started)
authenticates with ``x-api-key: <key>`` — *not* the Bearer scheme used
by every other LLM vendor in the catalog. What makes the credential
distinctive is the **mandatory** ``anthropic-version: <date>`` header
that pins the wire format on every request: omitting it returns a 400
``invalid_request_error`` rather than silently using a default. An
optional ``anthropic-beta`` header opts in to comma-separated beta
features (``message-batches-2024-09-24``, ``prompt-caching-2024-07-31``,
``computer-use-2025-01-24``, ...).

This is the first non-Bearer header-pair credential in the catalog —
distinct from OpenAI's ``Authorization: Bearer`` shape.

The self-test calls ``GET /v1/models`` which returns 200 + the model
list on a valid key.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: Final[str] = "https://api.anthropic.com"
_API_KEY_HEADER: Final[str] = "x-api-key"
_VERSION_HEADER: Final[str] = "anthropic-version"
_BETA_HEADER: Final[str] = "anthropic-beta"
_DEFAULT_VERSION: Final[str] = "2023-06-01"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class AnthropicApiCredential(BaseCredentialType):
    """Inject ``x-api-key`` + mandatory ``anthropic-version`` header pair."""

    slug: ClassVar[str] = "weftlyflow.anthropic_api"
    display_name: ClassVar[str] = "Anthropic API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.anthropic.com/en/api/getting-started"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Anthropic API key (sk-ant-...).",
            type_options={"password": True},
        ),
        PropertySchema(
            name="anthropic_version",
            display_name="Anthropic Version",
            type="string",
            required=True,
            default=_DEFAULT_VERSION,
            description="Mandatory 'anthropic-version' wire-format date pin.",
        ),
        PropertySchema(
            name="anthropic_beta",
            display_name="Beta Features",
            type="string",
            required=False,
            description="Comma-separated 'anthropic-beta' feature flags.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``x-api-key`` + ``anthropic-version`` (+ optional beta header)."""
        api_key = str(creds.get("api_key", "")).strip()
        request.headers[_API_KEY_HEADER] = api_key
        version = str(creds.get("anthropic_version", "")).strip() or _DEFAULT_VERSION
        request.headers[_VERSION_HEADER] = version
        beta = str(creds.get("anthropic_beta", "")).strip()
        if beta:
            request.headers[_BETA_HEADER] = beta
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v1/models`` and report the outcome."""
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        version = str(creds.get("anthropic_version") or _DEFAULT_VERSION).strip()
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}/v1/models",
                    headers={
                        _API_KEY_HEADER: api_key,
                        _VERSION_HEADER: version,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"anthropic rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = AnthropicApiCredential
