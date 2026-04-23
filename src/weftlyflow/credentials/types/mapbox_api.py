"""Mapbox API credential — ``access_token`` as a query parameter (not header).

Mapbox (https://docs.mapbox.com/api/overview/#access-tokens-and-token-scopes)
uniquely authenticates via a URL query string: every request carries
``?access_token=<pk.*|sk.*>``. There is *no* ``Authorization`` header
scheme accepted by the public APIs — the token ships in the URL.

This is the first catalog credential that mutates the URL rather than
the headers. Public tokens (``pk.*``) are safe to ship to browsers;
secret tokens (``sk.*``) grant write/uploads access and must never leak.

The self-test calls ``GET /tokens/v2`` which returns 200 + the token's
own metadata when valid and 401 otherwise.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_BASE_URL: Final[str] = "https://api.mapbox.com"
_QUERY_PARAM: Final[str] = "access_token"
_TEST_PATH: Final[str] = "/tokens/v2"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class MapboxApiCredential(BaseCredentialType):
    """Inject ``access_token=<token>`` into the outgoing URL."""

    slug: ClassVar[str] = "weftlyflow.mapbox_api"
    display_name: ClassVar[str] = "Mapbox API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.mapbox.com/api/overview/#access-tokens-and-token-scopes"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_token",
            display_name="Access Token",
            type="string",
            required=True,
            description="Mapbox access token (pk.* public or sk.* secret).",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Append ``access_token=<token>`` to the outgoing URL's query string."""
        token = str(creds.get("access_token", "")).strip()
        params = dict(request.url.params)
        params[_QUERY_PARAM] = token
        request.url = request.url.copy_with(params=params)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /tokens/v2`` and report the outcome."""
        token = str(creds.get("access_token") or "").strip()
        if not token:
            return CredentialTestResult(ok=False, message="access_token is empty")
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_BASE_URL}{_TEST_PATH}",
                    params={_QUERY_PARAM: token},
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"mapbox rejected token: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = MapboxApiCredential
