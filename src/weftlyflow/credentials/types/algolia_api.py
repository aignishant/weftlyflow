"""Algolia API credential — dual ``X-Algolia-*`` headers + derived host.

Algolia's Search & Indexing REST API
(https://www.algolia.com/doc/rest-api/) signs every request with two
custom headers — ``X-Algolia-API-Key`` and ``X-Algolia-Application-Id``
— and expects them to hit a per-application host
(``<application_id>-dsn.algolia.net`` for search, ``<application_id>.algolia.net``
for write ops). The node layer composes the host from the credential's
application_id.

The self-test calls ``GET /1/keys/<api_key>`` which returns the ACL of
the key currently in use.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_TIMEOUT_SECONDS: float = 10.0


class AlgoliaApiCredential(BaseCredentialType):
    """Inject both ``X-Algolia-API-Key`` and ``X-Algolia-Application-Id``."""

    slug: ClassVar[str] = "weftlyflow.algolia_api"
    display_name: ClassVar[str] = "Algolia API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://www.algolia.com/doc/guides/security/api-keys/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="application_id",
            display_name="Application ID",
            type="string",
            required=True,
            description="Algolia Application ID (10-char uppercase).",
            placeholder="YourAppID",
        ),
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Admin or search-only API key.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set both ``X-Algolia-API-Key`` and ``X-Algolia-Application-Id`` headers."""
        app_id = str(creds.get("application_id", "")).strip()
        key = str(creds.get("api_key", "")).strip()
        request.headers["X-Algolia-Application-Id"] = app_id
        request.headers["X-Algolia-API-Key"] = key
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Probe ``GET /1/keys/<api_key>`` on the per-app host."""
        app_id = str(creds.get("application_id") or "").strip()
        key = str(creds.get("api_key") or "").strip()
        if not app_id:
            return CredentialTestResult(ok=False, message="application_id is empty")
        if not key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        url = f"https://{app_id}-dsn.algolia.net/1/keys/{key}"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
                    headers={
                        "X-Algolia-Application-Id": app_id,
                        "X-Algolia-API-Key": key,
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"algolia rejected credentials: HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        acl_summary = ""
        if isinstance(payload, dict):
            acl = payload.get("acl")
            if isinstance(acl, list) and acl:
                acl_summary = ",".join(str(x) for x in acl[:3])
        suffix = f" (acl: {acl_summary})" if acl_summary else ""
        return CredentialTestResult(ok=True, message=f"authenticated{suffix}")


TYPE = AlgoliaApiCredential
