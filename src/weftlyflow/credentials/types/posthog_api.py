"""PostHog project-API-key credential — key lives inside the request body.

PostHog's capture endpoints (``/capture``, ``/batch``, ``/decide``)
authenticate by placing the **project API key** in the ``api_key``
field **of the JSON body**, not in a header or query parameter. This
is the only occurrence of "credential material in the request body" in
the catalog.

Because of this, :meth:`inject` is a no-op — credential placement is
performed by the node, which folds ``api_key`` into the body right
before dispatch so a single credential row can serve many operations.

Optional ``personal_api_key`` is used for management endpoints
(``/api/projects``, ``/api/event_definitions``) as
``Authorization: Bearer <personal_api_key>`` and is stored alongside
the project key for UI ergonomics.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEFAULT_HOST: str = "https://us.i.posthog.com"
_TEST_TIMEOUT_SECONDS: float = 10.0


class PostHogApiCredential(BaseCredentialType):
    """Hold PostHog project + personal keys. Injection is a no-op."""

    slug: ClassVar[str] = "weftlyflow.posthog_api"
    display_name: ClassVar[str] = "PostHog API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://posthog.com/docs/api"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="project_api_key",
            display_name="Project API Key",
            type="string",
            required=True,
            type_options={"password": True},
            description="Public project key (phc_...) — carried inside the request body.",
        ),
        PropertySchema(
            name="personal_api_key",
            display_name="Personal API Key",
            type="string",
            required=False,
            type_options={"password": True},
            description="Personal key (phx_...) for management endpoints; Bearer auth.",
        ),
        PropertySchema(
            name="host",
            display_name="PostHog Host",
            type="string",
            required=False,
            default=_DEFAULT_HOST,
            description="Override for self-hosted or EU-cloud deployments.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Return ``request`` unchanged — PostHog auth rides inside the body."""
        del creds
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``/decide`` with the project key to validate the credential."""
        project_key = str(creds.get("project_api_key", "")).strip()
        if not project_key:
            return CredentialTestResult(
                ok=False, message="project_api_key is required",
            )
        host = str(creds.get("host", "") or _DEFAULT_HOST).rstrip("/")
        url = f"{host}/decide/?v=3"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    url,
                    json={"api_key": project_key, "distinct_id": "weftlyflow-probe"},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"posthog rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="project_api_key valid")


TYPE = PostHogApiCredential
