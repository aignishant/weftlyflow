"""Google Analytics 4 Measurement Protocol credential — dual-query-param auth.

GA4's Measurement Protocol (https://developers.google.com/analytics/devguides/collection/protocol/ga4/)
authenticates server-side event ingestion with **two query parameters**
on every call:

* ``measurement_id`` — the public GA4 stream identifier (``G-XXXXXXXX``).
* ``api_secret`` — a per-stream secret generated in the Admin UI.

There is no ``Authorization`` header at all; both values must ride in
the URL's query string. This is a strictly different shape from
Pipedrive's single-token ``?api_token=`` or Trello's dual
``?key=&token=`` because GA4 pairs a public stream identifier with a
secret rather than two opaque tokens — validation is host-side against
the stream, not the pair.

:meth:`inject` appends both parameters to the request URL; the node
therefore does not need to touch the query itself.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEBUG_URL: str = "https://www.google-analytics.com/debug/mp/collect"
_TEST_TIMEOUT_SECONDS: float = 10.0


class Ga4MeasurementCredential(BaseCredentialType):
    """Inject ``measurement_id`` and ``api_secret`` as query parameters."""

    slug: ClassVar[str] = "weftlyflow.ga4_measurement"
    display_name: ClassVar[str] = "GA4 Measurement Protocol"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.google.com/analytics/devguides/collection/protocol/ga4/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="measurement_id",
            display_name="Measurement ID",
            type="string",
            required=True,
            description="GA4 stream identifier, e.g. G-XXXXXXXX.",
        ),
        PropertySchema(
            name="api_secret",
            display_name="API Secret",
            type="string",
            required=True,
            type_options={"password": True},
            description="Per-stream secret generated in the GA4 Admin UI.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Append ``measurement_id`` + ``api_secret`` to ``request`` URL query."""
        measurement_id = str(creds.get("measurement_id", "")).strip()
        api_secret = str(creds.get("api_secret", "")).strip()
        request.url = request.url.copy_merge_params(
            {"measurement_id": measurement_id, "api_secret": api_secret},
        )
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Post an empty event batch to ``/debug/mp/collect`` and inspect validation."""
        measurement_id = str(creds.get("measurement_id", "")).strip()
        api_secret = str(creds.get("api_secret", "")).strip()
        if not measurement_id or not api_secret:
            return CredentialTestResult(
                ok=False, message="measurement_id and api_secret are required",
            )
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    _DEBUG_URL,
                    params={
                        "measurement_id": measurement_id, "api_secret": api_secret,
                    },
                    json={"client_id": "weftlyflow.test", "events": []},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"ga4 rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="ga4 credentials accepted")


TYPE = Ga4MeasurementCredential
