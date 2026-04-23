"""Contentful credential — Bearer with **split base URL** (CMA vs CDA).

Contentful (https://www.contentful.com/developers/docs/references/authentication/)
ships two top-level REST APIs that share a Bearer token scheme but
serve from different hostnames:

* ``api.contentful.com`` — Content Management API (CMA): writes,
  publishes, and reads draft content using a Personal Access Token
  (``CFPAT-...``).
* ``cdn.contentful.com`` — Content Delivery API (CDA): read-only
  published content via a Delivery Token.

The credential stores a single ``api_token`` used as the Bearer and a
``space_id`` + ``environment`` pair used to build the path prefix
``/spaces/{space}/environments/{env}``. Callers pick which host to hit
per-operation; a query-param ``?environment=master`` override is *not*
supported — the environment is always in the path.

The self-test calls the CMA ``GET /spaces/{space}`` which returns 200
for a token scoped to the space.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_MANAGEMENT_HOST: Final[str] = "https://api.contentful.com"
_DELIVERY_HOST: Final[str] = "https://cdn.contentful.com"
_DEFAULT_ENVIRONMENT: Final[str] = "master"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class ContentfulApiCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer <token>`` (host split per-call)."""

    slug: ClassVar[str] = "weftlyflow.contentful_api"
    display_name: ClassVar[str] = "Contentful API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://www.contentful.com/developers/docs/references/authentication/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_token",
            display_name="API Token",
            type="string",
            required=True,
            description="CMA Personal Access Token (CFPAT-*) or CDA Delivery Token.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="space_id",
            display_name="Space ID",
            type="string",
            required=True,
            description="Target space id (e.g. ``k8c3tk01nr3j``).",
        ),
        PropertySchema(
            name="environment",
            display_name="Environment",
            type="string",
            required=True,
            default=_DEFAULT_ENVIRONMENT,
            description="Environment alias (default: ``master``).",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: Bearer <api_token>``."""
        token = str(creds.get("api_token", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call CMA ``GET /spaces/{space_id}`` and report the outcome."""
        token = str(creds.get("api_token") or "").strip()
        space_id = str(creds.get("space_id") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="api_token is empty")
        if not space_id:
            return CredentialTestResult(ok=False, message="space_id is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_MANAGEMENT_HOST}/spaces/{space_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"contentful rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = ContentfulApiCredential
