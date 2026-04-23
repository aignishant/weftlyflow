"""Alpaca Markets credential — dual ``APCA-API-*`` headers + env routing.

Alpaca (https://docs.alpaca.markets/) is the catalog's first brokerage
integration that splits auth across **two named headers** —
``APCA-API-KEY-ID`` and ``APCA-API-SECRET-KEY`` — *and* routes the
base URL through a per-credential ``environment`` field (paper vs
live). This is strictly different from the single-header Bearer + env
pattern (Plaid) and from the dual-header equal-peer patterns
(Cloudflare, Datadog) because Alpaca's two headers play distinct
server-side roles: one identifies the key, the other proves
possession of the secret.

:meth:`inject` unconditionally emits both headers; the node reads
``environment`` to pick ``paper-api.alpaca.markets`` or
``api.alpaca.markets``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertyOption, PropertySchema

_HOSTS: dict[str, str] = {
    "paper": "https://paper-api.alpaca.markets",
    "live": "https://api.alpaca.markets",
}
_DEFAULT_ENVIRONMENT: str = "paper"
_TEST_TIMEOUT_SECONDS: float = 10.0


class AlpacaApiCredential(BaseCredentialType):
    """Hold Alpaca key/secret and emit the dual ``APCA-API-*`` headers."""

    slug: ClassVar[str] = "weftlyflow.alpaca_api"
    display_name: ClassVar[str] = "Alpaca Markets API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.alpaca.markets/docs/getting-started"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key_id",
            display_name="API Key ID",
            type="string",
            required=True,
            description="Alpaca API key identifier (APCA-API-KEY-ID header).",
        ),
        PropertySchema(
            name="api_secret_key",
            display_name="API Secret Key",
            type="string",
            required=True,
            type_options={"password": True},
            description="Alpaca API secret (APCA-API-SECRET-KEY header).",
        ),
        PropertySchema(
            name="environment",
            display_name="Environment",
            type="options",
            required=True,
            default=_DEFAULT_ENVIRONMENT,
            options=[
                PropertyOption(value="paper", label="Paper"),
                PropertyOption(value="live", label="Live"),
            ],
            description="Routes to paper-api.alpaca.markets vs api.alpaca.markets.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Attach the pair of APCA-API-* headers to ``request``."""
        request.headers["APCA-API-KEY-ID"] = str(creds.get("api_key_id", "")).strip()
        request.headers["APCA-API-SECRET-KEY"] = str(creds.get("api_secret_key", "")).strip()
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``/v2/account`` (trading API) to verify both headers."""
        key_id = str(creds.get("api_key_id", "")).strip()
        secret = str(creds.get("api_secret_key", "")).strip()
        if not key_id or not secret:
            return CredentialTestResult(
                ok=False, message="api_key_id and api_secret_key are required",
            )
        host = host_for(creds.get("environment"))
        headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{host}/v2/account", headers=headers)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"alpaca rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="alpaca credentials valid")


def host_for(environment: str | None) -> str:
    """Return the Alpaca trading-API host for ``environment`` (paper/live)."""
    env = (environment or _DEFAULT_ENVIRONMENT).strip().lower()
    return _HOSTS.get(env, _HOSTS[_DEFAULT_ENVIRONMENT])


TYPE = AlpacaApiCredential
