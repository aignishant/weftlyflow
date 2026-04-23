"""Binance Spot credential — HMAC-SHA256 signature in query parameter.

Binance Spot (https://developers.binance.com/docs/binance-spot-api-docs/)
is the catalog's first integration that injects its signature as a
**hex-encoded query parameter** rather than a header. Every "SIGNED"
endpoint call carries:

* ``X-MBX-APIKEY`` — the public API key, added via :meth:`inject`.
* ``timestamp``    — current Unix time in **milliseconds**, appended by
  the node before signing.
* ``signature``    — ``hex(HMAC-SHA256(api_secret, total_params))``
  where ``total_params`` is the URL-encoded query string concatenated
  with the URL-encoded body (if any).

The credential deliberately keeps :meth:`inject` minimal — it only sets
the API-key header. The HMAC is computed by :func:`sign_query`, which
the node invokes after it has fully assembled the request's query and
body. This split keeps public (unsigned) endpoints clean while letting
the trading operations reuse the same credential.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertyOption, PropertySchema

_HOSTS: dict[str, str] = {
    "live": "https://api.binance.com",
    "testnet": "https://testnet.binance.vision",
}
_DEFAULT_ENVIRONMENT: str = "live"
_TEST_TIMEOUT_SECONDS: float = 10.0


class BinanceApiCredential(BaseCredentialType):
    """Hold Binance API key + secret and emit the ``X-MBX-APIKEY`` header."""

    slug: ClassVar[str] = "weftlyflow.binance_api"
    display_name: ClassVar[str] = "Binance Spot API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.binance.com/docs/binance-spot-api-docs/rest-api"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Binance public API key (sent as X-MBX-APIKEY).",
        ),
        PropertySchema(
            name="api_secret",
            display_name="API Secret",
            type="string",
            required=True,
            type_options={"password": True},
            description="Binance HMAC-SHA256 signing key.",
        ),
        PropertySchema(
            name="environment",
            display_name="Environment",
            type="options",
            required=True,
            default=_DEFAULT_ENVIRONMENT,
            options=[
                PropertyOption(value="live", label="Live"),
                PropertyOption(value="testnet", label="Testnet"),
            ],
            description="Selects host — api.binance.com vs testnet.binance.vision.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Add ``X-MBX-APIKEY`` to ``request`` — signing is a node concern."""
        api_key = str(creds.get("api_key", "")).strip()
        request.headers["X-MBX-APIKEY"] = api_key
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``/api/v3/account`` (SIGNED) to verify both key and secret."""
        api_key = str(creds.get("api_key", "")).strip()
        api_secret = str(creds.get("api_secret", "")).strip()
        if not api_key or not api_secret:
            return CredentialTestResult(
                ok=False, message="api_key and api_secret are required",
            )
        env = str(creds.get("environment") or _DEFAULT_ENVIRONMENT).strip()
        host = _HOSTS.get(env, _HOSTS[_DEFAULT_ENVIRONMENT])
        timestamp_ms = str(int(time.time() * 1000))
        query = f"timestamp={timestamp_ms}"
        signature = sign_query(api_secret=api_secret, total_params=query)
        url = f"{host}/api/v3/account?{query}&signature={signature}"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers={"X-MBX-APIKEY": api_key})
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"binance rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="binance credentials valid")


def sign_query(*, api_secret: str, total_params: str) -> str:
    """Return ``hex(HMAC-SHA256(api_secret, total_params))``.

    ``total_params`` is the URL-encoded query string concatenated with
    the URL-encoded body, exactly as Binance documents for SIGNED
    endpoints. The node assembles this string and passes it here —
    the credential does not know request semantics.
    """
    return hmac.new(
        api_secret.encode(), total_params.encode(), hashlib.sha256,
    ).hexdigest()


def host_for(environment: str | None) -> str:
    """Return the Binance REST host for ``environment`` (live/testnet)."""
    env = (environment or _DEFAULT_ENVIRONMENT).strip().lower()
    return _HOSTS.get(env, _HOSTS[_DEFAULT_ENVIRONMENT])


TYPE = BinanceApiCredential
