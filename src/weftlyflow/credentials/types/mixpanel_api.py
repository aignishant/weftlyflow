"""Mixpanel API credential — project token + service-account api_secret.

Mixpanel draws a line between *ingestion* and *management* endpoints.

* Ingestion (``/track``, ``/engage``, ``/groups``) authenticates by
  embedding the **project token** as ``token`` inside each event
  payload — not as a header. The node folds the token in at dispatch
  time; this credential's :meth:`inject` is therefore a **no-op**
  because no header/query/url mutation is required.
* Management and high-volume import endpoints (``/import``,
  ``/query``) use HTTP Basic auth with the **service-account API
  secret** as the username and an empty password.

We store both fields on a single credential and let the node choose
which one to consume based on the operation.
"""

from __future__ import annotations

import base64
import json
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_URL: str = "https://api.mixpanel.com/track"
_TEST_TIMEOUT_SECONDS: float = 10.0


class MixpanelApiCredential(BaseCredentialType):
    """Hold Mixpanel project token + optional api_secret. Injection is a no-op."""

    slug: ClassVar[str] = "weftlyflow.mixpanel_api"
    display_name: ClassVar[str] = "Mixpanel API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.mixpanel.com/reference/ingestion-api-authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="project_token",
            display_name="Project Token",
            type="string",
            required=True,
            type_options={"password": True},
            description="Project-scoped token embedded in every event payload.",
        ),
        PropertySchema(
            name="api_secret",
            display_name="API Secret",
            type="string",
            required=False,
            type_options={"password": True},
            description="Service-account secret used as Basic-auth username for /import.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Return ``request`` unchanged — Mixpanel auth rides inside the body."""
        del creds  # intentionally unused — the node reads project_token directly
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Send a probe event; Mixpanel returns ``1`` for success, ``0`` otherwise."""
        token = str(creds.get("project_token", "")).strip()
        if not token:
            return CredentialTestResult(
                ok=False, message="project_token is required",
            )
        payload = {
            "event": "weftlyflow.credential_test",
            "properties": {"token": token, "distinct_id": "weftlyflow-probe"},
        }
        encoded = base64.b64encode(
            json.dumps(payload).encode("utf-8"),
        ).decode("ascii")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    _TEST_URL, params={"data": encoded},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"mixpanel rejected token: HTTP {response.status_code}",
            )
        body = response.text.strip()
        if body != "1":
            return CredentialTestResult(
                ok=False, message=f"mixpanel returned {body!r} — token rejected",
            )
        return CredentialTestResult(ok=True, message="project_token valid")


TYPE = MixpanelApiCredential
