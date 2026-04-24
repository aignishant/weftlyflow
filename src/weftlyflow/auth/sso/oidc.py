"""OpenID-Connect adapter (authorization-code flow).

Implements :class:`SSOProvider` on top of any IdP that advertises an OIDC
discovery document at ``<issuer>/.well-known/openid-configuration``. Tested
against Keycloak; should work unmodified with Google Workspace, Microsoft
Entra, Okta, and Auth0 because they all implement the spec.

What this adapter does:

1. Fetches + caches the discovery document on first use.
2. Fetches + caches the JWKS used to verify ID tokens.
3. Builds the authorization URL (client chooses the redirect URL; we carry
   the state token passed in by the caller).
4. On callback: exchanges ``code`` for a token set, verifies the ID token
   signature + issuer + audience + expiry, and returns a
   :class:`SSOUserInfo`.

What this adapter does **not** do:

* Nonce replay storage. We rely on the state token for CSRF protection and
  on the IdP's own anti-replay for nonces; a global replay cache is a
  future improvement and is called out in weftlyinfo.md §8b.
* User provisioning. The caller (router) decides whether to create, link,
  or reject the local user row.
* Refresh-token management. Weftlyflow mints its own JWTs; the IdP's
  refresh token is dropped after the handshake.
"""

from __future__ import annotations

import urllib.parse
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError

from weftlyflow.auth.sso.base import SSOError, SSOUserInfo


@dataclass(slots=True, frozen=True)
class OIDCConfig:
    """Static configuration for a single OIDC IdP."""

    issuer_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...] = ("openid", "email", "profile")


class OIDCProvider:
    """Adapter implementing :class:`SSOProvider` for OIDC IdPs."""

    name: str = "oidc"

    __slots__ = ("_config", "_discovery", "_http", "_jwks")

    def __init__(
        self,
        config: OIDCConfig,
        *,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """Bind the adapter to ``config``.

        Args:
            config: Issuer URL, client id/secret, redirect URI, scopes.
            http: Optional pre-built :class:`httpx.AsyncClient`. Injecting
                one lets tests mock the network without monkeypatching.
                When ``None``, a fresh client is created per request and
                closed afterwards.
        """
        self._config = config
        self._http = http
        self._discovery: dict[str, Any] | None = None
        self._jwks: JsonWebKey | None = None

    def authorization_url(self, *, state: str) -> str:
        """Return the IdP's ``authorization_endpoint`` URL with query params."""
        if self._discovery is None:
            msg = "OIDCProvider: call prime() before authorization_url()"
            raise SSOError(msg)
        endpoint = str(self._discovery["authorization_endpoint"])
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "scope": " ".join(self._config.scopes),
                "state": state,
            },
        )
        return f"{endpoint}?{query}"

    async def prime(self) -> None:
        """Pre-fetch the discovery document + JWKS.

        Call once at server startup. Skipping this just means the first
        login pays a cold-start latency hit; it's not a correctness issue.
        """
        await self._ensure_discovery()
        await self._ensure_jwks()

    async def complete(self, params: dict[str, str]) -> SSOUserInfo:
        """Exchange ``params["code"]`` for a verified :class:`SSOUserInfo`.

        Raises:
            SSOError: The IdP returned an explicit error, the token
                exchange failed, or the ID token failed verification.
        """
        if "error" in params:
            msg = f"IdP returned error: {params.get('error_description') or params['error']}"
            raise SSOError(msg)
        code = params.get("code")
        if not code:
            msg = "IdP callback missing 'code' parameter"
            raise SSOError(msg)

        await self._ensure_discovery()
        await self._ensure_jwks()

        token_endpoint = str(self._require_discovery()["token_endpoint"])
        token_set = await self._exchange_code(token_endpoint, code)
        id_token = token_set.get("id_token")
        if not id_token:
            msg = "IdP token response missing id_token"
            raise SSOError(msg)
        claims = self._verify_id_token(id_token)

        email = str(claims.get("email", "")).lower()
        if not email:
            msg = "IdP ID token missing 'email' claim — add 'email' to scopes"
            raise SSOError(msg)
        verified = bool(claims.get("email_verified", False))
        return SSOUserInfo(
            subject=str(claims["sub"]),
            email=email,
            email_verified=verified,
            issuer=str(claims["iss"]),
            display_name=_coalesce_name(claims),
        )

    async def _ensure_discovery(self) -> None:
        if self._discovery is not None:
            return
        url = self._config.issuer_url.rstrip("/") + "/.well-known/openid-configuration"
        async with self._client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            self._discovery = dict(resp.json())

    async def _ensure_jwks(self) -> None:
        if self._jwks is not None:
            return
        jwks_uri = str(self._require_discovery()["jwks_uri"])
        async with self._client() as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            self._jwks = JsonWebKey.import_key_set(resp.json())

    async def _exchange_code(self, token_endpoint: str, code: str) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._config.redirect_uri,
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
        }
        async with self._client() as client:
            resp = await client.post(
                token_endpoint,
                data=data,
                headers={"Accept": "application/json"},
            )
            if resp.status_code >= HTTPStatus.BAD_REQUEST:
                msg = f"IdP token exchange failed: {resp.status_code} {resp.text[:200]}"
                raise SSOError(msg)
            return dict(resp.json())

    def _verify_id_token(self, id_token: str) -> dict[str, Any]:
        if self._jwks is None:
            msg = "OIDCProvider: JWKS not loaded"
            raise SSOError(msg)
        try:
            claims = JsonWebToken(["RS256", "ES256"]).decode(id_token, self._jwks)
            claims.validate()
        except JoseError as exc:
            msg = f"ID token verification failed: {exc}"
            raise SSOError(msg) from exc

        if claims.get("iss") != self._config.issuer_url.rstrip("/"):
            # Permit trailing-slash drift: normalise both sides before comparing.
            expected = self._config.issuer_url.rstrip("/")
            if str(claims.get("iss", "")).rstrip("/") != expected:
                msg = "ID token issuer does not match configured issuer"
                raise SSOError(msg)

        aud = claims.get("aud")
        ok = aud == self._config.client_id or (
            isinstance(aud, list) and self._config.client_id in aud
        )
        if not ok:
            msg = "ID token audience does not include this client"
            raise SSOError(msg)
        return dict(claims)

    def _require_discovery(self) -> dict[str, Any]:
        if self._discovery is None:
            msg = "OIDCProvider: discovery document not loaded"
            raise SSOError(msg)
        return self._discovery

    def _client(self) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        if self._http is not None:
            return _BorrowedClient(self._http)
        return httpx.AsyncClient(timeout=httpx.Timeout(10.0))


class _BorrowedClient:
    """Wrap an injected client so ``async with`` does not close it."""

    __slots__ = ("_client",)

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _coalesce_name(claims: dict[str, Any]) -> str | None:
    for key in ("name", "preferred_username", "given_name"):
        value = claims.get(key)
        if value:
            return str(value)
    return None
