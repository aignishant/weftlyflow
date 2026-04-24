"""Qdrant credential — base URL + optional ``api-key`` header.

Qdrant (https://qdrant.tech) ships as a self-hostable vector database
and as a managed Cloud offering. A bare self-host deployment has no
authentication by default; managed Cloud and any production-ready
deploy gate access with an ``api-key`` header. The same credential
covers both: :meth:`QdrantApiCredential.inject` only sets the header
when ``api_key`` is non-empty.

The self-test calls ``GET /readyz`` which Qdrant returns ``200 ok``
on any healthy node without needing a specific collection.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEFAULT_BASE_URL: Final[str] = "http://localhost:6333"
_READY_PATH: Final[str] = "/readyz"
_API_KEY_HEADER: Final[str] = "api-key"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def base_url_from(raw_base_url: str) -> str:
    """Normalise a user-supplied Qdrant base URL.

    Empty string -> the out-of-box self-host default
    ``http://localhost:6333``. Trailing slashes are stripped and a
    missing scheme is assumed to be ``http://``.
    """
    cleaned = raw_base_url.strip().rstrip("/")
    if not cleaned:
        return _DEFAULT_BASE_URL
    if "://" not in cleaned:
        cleaned = f"http://{cleaned}"
    return cleaned


class QdrantApiCredential(BaseCredentialType):
    """Qdrant base URL + optional ``api-key`` header auth."""

    slug: ClassVar[str] = "weftlyflow.qdrant_api"
    display_name: ClassVar[str] = "Qdrant"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://api.qdrant.tech/api-reference"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            required=False,
            default=_DEFAULT_BASE_URL,
            description=(
                "Qdrant server URL; defaults to 'http://localhost:6333'."
            ),
        ),
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=False,
            description=(
                "Optional api-key header; required by Qdrant Cloud and "
                "any auth-enabled self-host."
            ),
            type_options={"password": True},
        ),
    ]

    async def inject(
        self, creds: dict[str, Any], request: httpx.Request,
    ) -> httpx.Request:
        """Set the ``api-key`` header when ``api_key`` is non-empty."""
        key = str(creds.get("api_key") or "").strip()
        if key:
            request.headers[_API_KEY_HEADER] = key
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /readyz`` against the configured base URL."""
        base = base_url_from(str(creds.get("base_url") or ""))
        key = str(creds.get("api_key") or "").strip()
        headers: dict[str, str] = {"Accept": "application/json"}
        if key:
            headers[_API_KEY_HEADER] = key
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{base}{_READY_PATH}", headers=headers)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"qdrant rejected request: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="reachable")


TYPE = QdrantApiCredential
