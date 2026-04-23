"""Datadog credential — dual ``DD-API-KEY`` + ``DD-APPLICATION-KEY`` headers.

Datadog (https://docs.datadoghq.com/api/latest/authentication/) splits
authentication across *two* cooperating keys:

* ``DD-API-KEY`` — an org-scoped API key that authorizes ingest and
  read endpoints.
* ``DD-APPLICATION-KEY`` — a user-scoped application key required for
  most management endpoints (monitors, dashboards, metric queries).

Both headers are sent together on most requests; send-only ingest
paths tolerate an empty application key. The distinctive shape here is
the header pair — Datadog is the only widespread SaaS that requires
two independent keys on the *same* request rather than a single
composite token.

The credential also carries a ``site`` field (e.g. ``us1``, ``eu1``,
``us3``, ``us5``, ``ap1``, ``gov``) that drives per-region host
derivation so nodes stay host-agnostic.

The self-test calls ``GET /api/v1/validate``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertyOption, PropertySchema

_API_KEY_HEADER: str = "DD-API-KEY"
_APP_KEY_HEADER: str = "DD-APPLICATION-KEY"
_TEST_TIMEOUT_SECONDS: float = 10.0

_SITE_HOSTS: dict[str, str] = {
    "us1": "api.datadoghq.com",
    "us3": "api.us3.datadoghq.com",
    "us5": "api.us5.datadoghq.com",
    "eu1": "api.datadoghq.eu",
    "ap1": "api.ap1.datadoghq.com",
    "gov": "api.ddog-gov.com",
}


def site_host_from(site: str) -> str:
    """Return ``https://<host>`` for a Datadog ``site`` code.

    Accepts either a short code (``us1``, ``eu1``) or a bare host
    (``api.datadoghq.com``) for forward-compatibility with new
    regions.
    """
    cleaned = site.strip().lower().rstrip("/")
    if not cleaned:
        msg = "Datadog: 'site' is required"
        raise ValueError(msg)
    if cleaned in _SITE_HOSTS:
        return f"https://{_SITE_HOSTS[cleaned]}"
    if "://" in cleaned:
        return cleaned
    if "." in cleaned:
        return f"https://{cleaned}"
    msg = (
        f"Datadog: unknown site {site!r}; expected one of "
        f"{sorted(_SITE_HOSTS)!r} or a full hostname"
    )
    raise ValueError(msg)


class DatadogApiCredential(BaseCredentialType):
    """Inject the ``DD-API-KEY`` + ``DD-APPLICATION-KEY`` pair."""

    slug: ClassVar[str] = "weftlyflow.datadog_api"
    display_name: ClassVar[str] = "Datadog API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.datadoghq.com/api/latest/authentication/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Org-scoped Datadog API key.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="application_key",
            display_name="Application Key",
            type="string",
            required=False,
            description=(
                "User-scoped application key — required for management "
                "endpoints (monitors, dashboards, metric queries)."
            ),
            type_options={"password": True},
        ),
        PropertySchema(
            name="site",
            display_name="Site",
            type="options",
            required=True,
            default="us1",
            description="Datadog region; drives the per-site host.",
            options=[
                PropertyOption(value="us1", label="US1 (datadoghq.com)"),
                PropertyOption(value="us3", label="US3 (us3.datadoghq.com)"),
                PropertyOption(value="us5", label="US5 (us5.datadoghq.com)"),
                PropertyOption(value="eu1", label="EU1 (datadoghq.eu)"),
                PropertyOption(value="ap1", label="AP1 (ap1.datadoghq.com)"),
                PropertyOption(value="gov", label="GOV (ddog-gov.com)"),
            ],
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set both Datadog header keys on ``request``."""
        api_key = str(creds.get("api_key", "")).strip()
        app_key = str(creds.get("application_key", "")).strip()
        request.headers[_API_KEY_HEADER] = api_key
        if app_key:
            request.headers[_APP_KEY_HEADER] = app_key
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /api/v1/validate`` and report."""
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            base = site_host_from(str(creds.get("site") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        headers = {
            _API_KEY_HEADER: api_key,
            "Accept": "application/json",
        }
        app_key = str(creds.get("application_key") or "").strip()
        if app_key:
            headers[_APP_KEY_HEADER] = app_key
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}/api/v1/validate", headers=headers,
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"datadog rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = DatadogApiCredential
