"""Klaviyo API credential — custom ``Klaviyo-API-Key`` scheme + date-versioned header.

Klaviyo (https://developers.klaviyo.com/) introduces two wrinkles not
yet represented in the catalog:

* The ``Authorization`` header carries a **non-standard scheme name**:
  ``Authorization: Klaviyo-API-Key pk_xxx``. This is neither ``Bearer``
  nor ``Basic`` and would be rejected by a generic Bearer credential.
* Every request MUST include a ``revision: YYYY-MM-DD`` header
  pinning the API contract version; Klaviyo rejects calls that omit
  it. This is a date-based versioning scheme rather than a semantic
  version, so we expose it as a free-form string with a current
  default.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEFAULT_REVISION: str = "2024-10-15"
_ACCOUNT_URL: str = "https://a.klaviyo.com/api/accounts"
_TEST_TIMEOUT_SECONDS: float = 10.0


class KlaviyoApiCredential(BaseCredentialType):
    """Inject the custom ``Klaviyo-API-Key`` auth scheme + revision header."""

    slug: ClassVar[str] = "weftlyflow.klaviyo_api"
    display_name: ClassVar[str] = "Klaviyo API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.klaviyo.com/en/reference/api_overview"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="Private API Key",
            type="string",
            required=True,
            type_options={"password": True},
            description="Private API key (starts with 'pk_').",
        ),
        PropertySchema(
            name="revision",
            display_name="API Revision",
            type="string",
            required=True,
            default=_DEFAULT_REVISION,
            description="Date-based API version (YYYY-MM-DD) — mandatory on every call.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set the custom ``Klaviyo-API-Key`` Authorization + ``revision`` headers."""
        key = str(creds.get("api_key", "")).strip()
        revision = str(creds.get("revision") or _DEFAULT_REVISION).strip() or _DEFAULT_REVISION
        request.headers["Authorization"] = f"Klaviyo-API-Key {key}"
        request.headers["revision"] = revision
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/accounts`` with the candidate credentials."""
        key = str(creds.get("api_key", "")).strip()
        if not key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        revision = str(creds.get("revision") or _DEFAULT_REVISION).strip() or _DEFAULT_REVISION
        headers = {
            "Authorization": f"Klaviyo-API-Key {key}",
            "revision": revision,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(_ACCOUNT_URL, headers=headers)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"klaviyo rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="klaviyo credentials valid")


TYPE = KlaviyoApiCredential
