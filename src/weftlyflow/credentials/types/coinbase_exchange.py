"""Coinbase Exchange credential — quad-header HMAC request signing.

Coinbase Exchange (https://docs.cdp.coinbase.com/exchange/docs/) is the
catalog's first integration to require **per-request HMAC signing** of
the request body — a fundamentally different shape from header/query
token auth. Every call carries four headers:

* ``CB-ACCESS-KEY``      — the API key.
* ``CB-ACCESS-SIGN``     — ``base64(HMAC-SHA256(base64_decode(secret),
                            timestamp + method + path + body))``.
* ``CB-ACCESS-TIMESTAMP``— current Unix time in **seconds**.
* ``CB-ACCESS-PASSPHRASE`` — the API-key passphrase.

Because the signature depends on the request's HTTP method, path (with
query string), and body, it cannot be precomputed — :meth:`inject`
reads those fields off the :class:`httpx.Request` and re-derives the
signature on every call. This is strictly distinct from AWS SigV4
(which signs a canonical request involving every header) and from
Coinbase Advanced Trade (which uses ES256 JWTs instead of HMAC).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import time
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_HOST: str = "https://api.exchange.coinbase.com"
_TEST_TIMEOUT_SECONDS: float = 10.0


class CoinbaseExchangeCredential(BaseCredentialType):
    """Sign every request with HMAC-SHA256 and emit four CB-ACCESS-* headers."""

    slug: ClassVar[str] = "weftlyflow.coinbase_exchange"
    display_name: ClassVar[str] = "Coinbase Exchange"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.cdp.coinbase.com/exchange/docs/rest-api-overview"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="Coinbase Exchange API key (CB-ACCESS-KEY).",
        ),
        PropertySchema(
            name="api_secret",
            display_name="API Secret",
            type="string",
            required=True,
            type_options={"password": True},
            description="Base64-encoded HMAC secret — decoded before signing.",
        ),
        PropertySchema(
            name="passphrase",
            display_name="Passphrase",
            type="string",
            required=True,
            type_options={"password": True},
            description="API-key passphrase chosen at key creation.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Compute HMAC-SHA256 signature and emit four ``CB-ACCESS-*`` headers."""
        api_key = str(creds.get("api_key", "")).strip()
        secret = str(creds.get("api_secret", "")).strip()
        passphrase = str(creds.get("passphrase", "")).strip()
        timestamp = str(int(time.time()))
        signature = _sign(
            secret=secret,
            timestamp=timestamp,
            method=request.method.upper(),
            path=_path_with_query(request.url),
            body=_body_text(request),
        )
        request.headers["CB-ACCESS-KEY"] = api_key
        request.headers["CB-ACCESS-SIGN"] = signature
        request.headers["CB-ACCESS-TIMESTAMP"] = timestamp
        request.headers["CB-ACCESS-PASSPHRASE"] = passphrase
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /accounts`` and verify the key can enumerate accounts."""
        api_key = str(creds.get("api_key", "")).strip()
        secret = str(creds.get("api_secret", "")).strip()
        passphrase = str(creds.get("passphrase", "")).strip()
        if not api_key or not secret or not passphrase:
            return CredentialTestResult(
                ok=False, message="api_key, api_secret and passphrase are required",
            )
        try:
            base64.b64decode(secret, validate=True)
        except (ValueError, binascii.Error):
            return CredentialTestResult(
                ok=False, message="api_secret is not valid base64",
            )
        timestamp = str(int(time.time()))
        signature = _sign(
            secret=secret, timestamp=timestamp, method="GET",
            path="/accounts", body="",
        )
        headers = {
            "CB-ACCESS-KEY": api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-PASSPHRASE": passphrase,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_HOST}/accounts", headers=headers,
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"coinbase rejected credentials: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="coinbase credentials valid")


def _sign(
    *, secret: str, timestamp: str, method: str, path: str, body: str,
) -> str:
    """Return ``base64(HMAC-SHA256(base64_decode(secret), prehash))``."""
    try:
        key = base64.b64decode(secret)
    except (ValueError, binascii.Error):
        key = secret.encode()
    message = f"{timestamp}{method}{path}{body}".encode()
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _path_with_query(url: httpx.URL) -> str:
    """Return the path plus (if any) ``?query`` — what Coinbase signs."""
    path = url.raw_path.decode() if isinstance(url.raw_path, bytes) else str(url.raw_path)
    return path or "/"


def _body_text(request: httpx.Request) -> str:
    """Return the request body as a string — Coinbase signs the exact bytes."""
    content = request.content
    if not content:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content)


TYPE = CoinbaseExchangeCredential
