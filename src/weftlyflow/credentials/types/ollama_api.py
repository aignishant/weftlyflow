"""Ollama credential — self-hosted base URL + optional bearer token.

Ollama (https://ollama.com) is a local-first LLM runtime. A fresh
install listens on ``http://localhost:11434`` with **no authentication**
— the default deployment target for self-hosted Weftlyflow. Users who
expose Ollama through a reverse proxy (caddy, nginx, tailscale funnel,
...) typically gate it with a bearer token; the optional ``api_key``
field on this credential covers that case.

This is the first optional-auth credential in the catalog: ``inject``
sets ``Authorization: Bearer <token>`` only when ``api_key`` is
non-empty, so the same credential works for both the out-of-box local
deployment and a token-protected remote one.

The self-test calls ``GET /api/tags`` which returns 200 + the installed
model list on any reachable Ollama (whether or not auth is configured).
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEFAULT_BASE_URL: Final[str] = "http://localhost:11434"
_TAGS_PATH: Final[str] = "/api/tags"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def base_url_from(raw_base_url: str) -> str:
    """Normalize ``raw_base_url`` — strip trailing slashes, assume ``http://`` when scheme absent.

    Args:
        raw_base_url: User-supplied base URL. Empty falls back to the
            documented Ollama default ``http://localhost:11434``.

    Raises:
        ValueError: never — an empty string is treated as the default.
    """
    cleaned = raw_base_url.strip().rstrip("/")
    if not cleaned:
        return _DEFAULT_BASE_URL
    if "://" not in cleaned:
        cleaned = f"http://{cleaned}"
    return cleaned


class OllamaApiCredential(BaseCredentialType):
    """Inject optional Bearer auth; pair it with a self-hosted base URL."""

    slug: ClassVar[str] = "weftlyflow.ollama_api"
    display_name: ClassVar[str] = "Ollama"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://github.com/ollama/ollama/blob/main/docs/api.md"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            required=False,
            default=_DEFAULT_BASE_URL,
            description="Ollama server URL; defaults to 'http://localhost:11434'.",
        ),
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=False,
            description="Optional bearer token when Ollama is behind an auth proxy.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <token>`` only when ``api_key`` is non-empty."""
        token = str(creds.get("api_key", "")).strip()
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/tags`` against the configured base URL."""
        base = base_url_from(str(creds.get("base_url") or ""))
        token = str(creds.get("api_key") or "").strip()
        headers: dict[str, str] = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{base}{_TAGS_PATH}", headers=headers)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"ollama rejected request: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        count = 0
        if isinstance(payload, dict):
            models = payload.get("models")
            if isinstance(models, list):
                count = len(models)
        return CredentialTestResult(ok=True, message=f"reachable ({count} model(s))")


TYPE = OllamaApiCredential
