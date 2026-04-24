"""Chroma credential — base URL + optional ``Authorization`` token.

Chroma (https://docs.trychroma.com) ships as a self-hostable vector
database behind a simple REST API. A bare self-host deployment has
no authentication by default; production deployments (and the
managed Chroma Cloud offering) gate access with an
``Authorization: Bearer <token>`` header. The same credential covers
both: :meth:`ChromaCredential.inject` only sets the header when the
configured ``token`` is non-empty.

v2 API paths are scoped by tenant and database
(``/api/v2/tenants/{tenant}/databases/{database}/collections/...``).
Both default to Chroma's out-of-the-box ``default_tenant`` /
``default_database`` but are exposed as credential properties so a
single API key can address multiple tenants without duplicating rows.

The self-test calls ``GET /api/v2/heartbeat`` which returns a JSON
``{nanosecond heartbeat: int}`` on any healthy node without needing
a specific tenant/database/collection.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEFAULT_BASE_URL: Final[str] = "http://localhost:8000"
_DEFAULT_TENANT: Final[str] = "default_tenant"
_DEFAULT_DATABASE: Final[str] = "default_database"
_HEARTBEAT_PATH: Final[str] = "/api/v2/heartbeat"
_AUTH_HEADER: Final[str] = "Authorization"
_AUTH_SCHEME: Final[str] = "Bearer"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def base_url_from(raw_base_url: str) -> str:
    """Normalise a user-supplied Chroma base URL.

    Empty string falls back to the out-of-box self-host default
    ``http://localhost:8000``. Trailing slashes are stripped and a
    missing scheme is assumed to be ``http://``.
    """
    cleaned = raw_base_url.strip().rstrip("/")
    if not cleaned:
        return _DEFAULT_BASE_URL
    if "://" not in cleaned:
        cleaned = f"http://{cleaned}"
    return cleaned


def tenant_from(raw_tenant: str) -> str:
    """Return the configured tenant or fall back to ``default_tenant``."""
    cleaned = raw_tenant.strip()
    return cleaned or _DEFAULT_TENANT


def database_from(raw_database: str) -> str:
    """Return the configured database or fall back to ``default_database``."""
    cleaned = raw_database.strip()
    return cleaned or _DEFAULT_DATABASE


class ChromaCredential(BaseCredentialType):
    """Chroma base URL + optional ``Authorization: Bearer`` token."""

    slug: ClassVar[str] = "weftlyflow.chroma"
    display_name: ClassVar[str] = "Chroma"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.trychroma.com/reference/python/client"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            required=False,
            default=_DEFAULT_BASE_URL,
            description=(
                "Chroma server URL; defaults to 'http://localhost:8000'."
            ),
        ),
        PropertySchema(
            name="token",
            display_name="Token",
            type="string",
            required=False,
            description=(
                "Optional bearer token; required by Chroma Cloud and "
                "any auth-enabled self-host."
            ),
            type_options={"password": True},
        ),
        PropertySchema(
            name="tenant",
            display_name="Tenant",
            type="string",
            required=False,
            default=_DEFAULT_TENANT,
            description="v2 API tenant; defaults to 'default_tenant'.",
        ),
        PropertySchema(
            name="database",
            display_name="Database",
            type="string",
            required=False,
            default=_DEFAULT_DATABASE,
            description="v2 API database; defaults to 'default_database'.",
        ),
    ]

    async def inject(
        self, creds: dict[str, Any], request: httpx.Request,
    ) -> httpx.Request:
        """Set ``Authorization: Bearer <token>`` when ``token`` is non-empty."""
        token = str(creds.get("token") or "").strip()
        if token:
            request.headers[_AUTH_HEADER] = f"{_AUTH_SCHEME} {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v2/heartbeat`` against the configured base URL."""
        base = base_url_from(str(creds.get("base_url") or ""))
        token = str(creds.get("token") or "").strip()
        headers: dict[str, str] = {"Accept": "application/json"}
        if token:
            headers[_AUTH_HEADER] = f"{_AUTH_SCHEME} {token}"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_HEARTBEAT_PATH}", headers=headers,
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"chroma rejected request: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="reachable")


TYPE = ChromaCredential
