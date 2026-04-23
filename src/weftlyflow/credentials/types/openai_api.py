"""OpenAI credential — Bearer + multi-dimensional tenant scoping headers.

OpenAI (https://platform.openai.com/docs/api-reference/authentication)
uses ``Authorization: Bearer <api_key>`` but optionally carries *two*
orthogonal scoping headers:

* ``OpenAI-Organization`` — legacy org-level scoping, used when a key
  has access to multiple organizations.
* ``OpenAI-Project`` — finer-grained project-level scoping introduced
  alongside sk-proj-* keys.

The distinctive shape here is the *pair* of scoping headers — other
Bearer providers either have no tenant header or a single one. Both
are optional at the credential level and omitted from the wire when
empty so default-scoped keys remain single-header.

The self-test calls ``GET /v1/models`` which returns a 200 with the
list of accessible models on valid keys and 401 otherwise.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: str = "https://api.openai.com"
_TEST_PATH: str = "/v1/models"
_TEST_TIMEOUT_SECONDS: float = 10.0
_ORG_HEADER: str = "OpenAI-Organization"
_PROJECT_HEADER: str = "OpenAI-Project"


class OpenAIApiCredential(BaseCredentialType):
    """Inject Bearer + optional ``OpenAI-Organization`` + ``OpenAI-Project``."""

    slug: ClassVar[str] = "weftlyflow.openai_api"
    display_name: ClassVar[str] = "OpenAI API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://platform.openai.com/docs/api-reference/authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="OpenAI API key (sk-... or sk-proj-...).",
            type_options={"password": True},
        ),
        PropertySchema(
            name="organization_id",
            display_name="Organization ID",
            type="string",
            required=False,
            description="Optional 'OpenAI-Organization' scoping header (org-...).",
        ),
        PropertySchema(
            name="project_id",
            display_name="Project ID",
            type="string",
            required=False,
            description="Optional 'OpenAI-Project' scoping header (proj_...).",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set Bearer auth + optional organization + project scoping headers."""
        token = str(creds.get("api_key", "")).strip()
        request.headers["Authorization"] = f"Bearer {token}"
        org_id = str(creds.get("organization_id", "")).strip()
        if org_id:
            request.headers[_ORG_HEADER] = org_id
        project_id = str(creds.get("project_id", "")).strip()
        if project_id:
            request.headers[_PROJECT_HEADER] = project_id
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v1/models`` and report the outcome."""
        token = str(creds.get("api_key") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="api_key is empty")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        org_id = str(creds.get("organization_id") or "").strip()
        if org_id:
            headers[_ORG_HEADER] = org_id
        project_id = str(creds.get("project_id") or "").strip()
        if project_id:
            headers[_PROJECT_HEADER] = project_id
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}{_TEST_PATH}", headers=headers,
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"openai rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = OpenAIApiCredential
