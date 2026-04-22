"""Supabase credential — dual ``apikey`` + ``Authorization: Bearer`` headers.

Supabase's REST surface (https://supabase.com/docs/guides/api) requires
*two* headers on every request that both carry the same API key: a
custom ``apikey`` header used by the Supabase gateway to route the
request to the right project, and a standard
``Authorization: Bearer <key>`` header used by PostgREST to authorize
the row-level-security context. Every project lives at its own
``https://<project>.supabase.co`` URL, so the credential carries both
the key and the project URL.

The self-test calls ``GET /rest/v1/`` which PostgREST responds to with
the OpenAPI spec for the project — a cheap reachability probe.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_REST_PATH: str = "/rest/v1/"
_TEST_TIMEOUT_SECONDS: float = 10.0


def project_url_from(raw_project_url: str) -> str:
    """Normalize ``raw_project_url`` to ``https://<host>`` (no trailing slash)."""
    cleaned = raw_project_url.strip().rstrip("/")
    if not cleaned:
        msg = "Supabase: 'project_url' is required"
        raise ValueError(msg)
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    return cleaned


class SupabaseApiCredential(BaseCredentialType):
    """Inject ``apikey`` + ``Authorization: Bearer`` (same key in both)."""

    slug: ClassVar[str] = "weftlyflow.supabase_api"
    display_name: ClassVar[str] = "Supabase API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://supabase.com/docs/guides/api#api-url-and-keys"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="service_role_key",
            display_name="API Key",
            type="string",
            required=True,
            description=(
                "Supabase service_role or anon key "
                "(prefer service_role for server-side workflows)."
            ),
            type_options={"password": True},
        ),
        PropertySchema(
            name="project_url",
            display_name="Project URL",
            type="string",
            required=True,
            description="Base URL, e.g. 'https://abcd.supabase.co'.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set both ``apikey`` and ``Authorization: Bearer`` headers."""
        key = str(creds.get("service_role_key", "")).strip()
        request.headers["apikey"] = key
        request.headers["Authorization"] = f"Bearer {key}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /rest/v1/`` and report."""
        key = str(creds.get("service_role_key") or "").strip()
        if not key:
            return CredentialTestResult(ok=False, message="service_role_key is empty")
        try:
            base = project_url_from(str(creds.get("project_url") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_REST_PATH}",
                    headers={
                        "apikey": key,
                        "Authorization": f"Bearer {key}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"supabase rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = SupabaseApiCredential
