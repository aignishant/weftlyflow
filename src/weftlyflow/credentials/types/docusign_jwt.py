"""DocuSign eSignature credential — RS256 JWT Grant flow.

DocuSign (https://developers.docusign.com/platform/auth/jwt/) uses
the OAuth 2.0 JWT Bearer grant: the client signs a short-lived JWT
assertion locally with an **RSA** private key and exchanges it at
``/oauth/token`` for a regular Bearer access token. This is strictly
distinct from:

* Ghost (HS256 — symmetric HMAC).
* Apple App Store Connect (ES256 — ECDSA, no token exchange).
* PayPal Client Credentials (no local signing, just HTTP Basic).

The JWT carries these claims:

* ``iss`` — integration key (client id in the DocuSign eSignature app).
* ``sub`` — user ID to impersonate.
* ``aud`` — ``account.docusign.com`` (live) or ``account-d.docusign.com`` (demo).
* ``iat`` — current time in seconds.
* ``exp`` — ``iat + 3600`` (DocuSign caps JWT lifetime at 1 hour).
* ``scope`` — space-separated list, typically ``signature impersonation``.

:meth:`inject` is a no-op — the node is expected to call
:func:`fetch_access_token` once at the start of execution and reuse
the Bearer across its dispatch loop.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any, ClassVar, Final

import httpx
from cryptography.exceptions import InvalidKey, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertyOption, PropertySchema

_OAUTH_HOSTS: Final[dict[str, str]] = {
    "demo": "https://account-d.docusign.com",
    "live": "https://account.docusign.com",
}
_AUDIENCE_HOSTS: Final[dict[str, str]] = {
    "demo": "account-d.docusign.com",
    "live": "account.docusign.com",
}
_DEFAULT_ENVIRONMENT: Final[str] = "demo"
_TOKEN_PATH: Final[str] = "/oauth/token"
_GRANT_TYPE: Final[str] = "urn:ietf:params:oauth:grant-type:jwt-bearer"
_DEFAULT_SCOPE: Final[str] = "signature impersonation"
_JWT_EXPIRY_SECONDS: Final[int] = 3600
_TEST_TIMEOUT_SECONDS: Final[float] = 15.0


def _b64url(data: bytes) -> str:
    """Base64url-encode ``data`` without padding — required by JWT."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _load_rsa_key(pem: str) -> RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm, InvalidKey) as exc:
        msg = f"DocuSign: private_key is not a valid PEM-encoded RSA key: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(key, RSAPrivateKey):
        msg = "DocuSign: private_key must be an RSA key"
        raise ValueError(msg)
    return key


def oauth_host_for(environment: str | None) -> str:
    """Return the DocuSign OAuth host for ``environment``."""
    env = (environment or _DEFAULT_ENVIRONMENT).strip().lower()
    return _OAUTH_HOSTS.get(env, _OAUTH_HOSTS[_DEFAULT_ENVIRONMENT])


def audience_for(environment: str | None) -> str:
    """Return the JWT ``aud`` claim host for ``environment``."""
    env = (environment or _DEFAULT_ENVIRONMENT).strip().lower()
    return _AUDIENCE_HOSTS.get(env, _AUDIENCE_HOSTS[_DEFAULT_ENVIRONMENT])


def build_jwt_assertion(
    *,
    integration_key: str,
    user_id: str,
    private_key_pem: str,
    audience: str,
    scope: str = _DEFAULT_SCOPE,
    now: int | None = None,
) -> str:
    """Mint a fresh RS256 JWT ready to exchange at DocuSign's token endpoint."""
    key = _load_rsa_key(private_key_pem)
    issued_at = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": integration_key,
        "sub": user_id,
        "aud": audience,
        "iat": issued_at,
        "exp": issued_at + _JWT_EXPIRY_SECONDS,
        "scope": scope,
    }
    header_seg = _b64url(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    claims_seg = _b64url(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    signing_input = f"{header_seg}.{claims_seg}".encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_seg}.{claims_seg}.{_b64url(signature)}"


async def fetch_access_token(
    client: httpx.AsyncClient,
    creds: dict[str, Any],
    *,
    scope: str = _DEFAULT_SCOPE,
) -> str:
    """Mint a JWT assertion and exchange it for a DocuSign Bearer token.

    Args:
        client: An ``httpx.AsyncClient`` whose ``base_url`` points at the
            DocuSign OAuth host (see :func:`oauth_host_for`).
        creds: The decrypted credential payload — must include
            ``integration_key``, ``user_id`` and ``private_key``.
        scope: Space-separated scope list for the exchange.

    Returns:
        The bearer access token string.

    Raises:
        ValueError: If fields are missing or DocuSign rejects the exchange.
    """
    integration_key = str(creds.get("integration_key") or "").strip()
    user_id = str(creds.get("user_id") or "").strip()
    private_key = str(creds.get("private_key") or "")
    if not integration_key or not user_id or not private_key.strip():
        msg = "DocuSign: integration_key, user_id and private_key are required"
        raise ValueError(msg)
    assertion = build_jwt_assertion(
        integration_key=integration_key,
        user_id=user_id,
        private_key_pem=private_key,
        audience=audience_for(creds.get("environment")),
        scope=scope,
    )
    response = await client.post(
        _TOKEN_PATH,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": _GRANT_TYPE, "assertion": assertion},
    )
    if response.status_code != httpx.codes.OK:
        msg = (
            f"DocuSign token endpoint rejected assertion: "
            f"HTTP {response.status_code}"
        )
        raise ValueError(msg)
    try:
        payload = response.json()
    except ValueError as exc:
        msg = "DocuSign token endpoint returned non-JSON body"
        raise ValueError(msg) from exc
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        msg = "DocuSign token endpoint omitted 'access_token'"
        raise ValueError(msg)
    return token


class DocuSignJwtCredential(BaseCredentialType):
    """Store integration_key + user_id + RSA key — tokens are fetched at runtime."""

    slug: ClassVar[str] = "weftlyflow.docusign_jwt"
    display_name: ClassVar[str] = "DocuSign eSignature (JWT Grant)"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.docusign.com/platform/auth/jwt/"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="integration_key",
            display_name="Integration Key",
            type="string",
            required=True,
            description="DocuSign app integration key (used as JWT iss claim).",
        ),
        PropertySchema(
            name="user_id",
            display_name="User ID",
            type="string",
            required=True,
            description="User GUID to impersonate (JWT sub claim).",
        ),
        PropertySchema(
            name="private_key",
            display_name="RSA Private Key (PEM)",
            type="string",
            required=True,
            type_options={"password": True, "rows": 14},
            description="PEM-encoded RSA private key — used to sign the JWT assertion.",
        ),
        PropertySchema(
            name="environment",
            display_name="Environment",
            type="options",
            required=True,
            default=_DEFAULT_ENVIRONMENT,
            options=[
                PropertyOption(value="demo", label="Demo / Developer Sandbox"),
                PropertyOption(value="live", label="Production"),
            ],
            description="Selects demo vs live DocuSign OAuth host.",
        ),
        PropertySchema(
            name="account_base_url",
            display_name="Account Base URL",
            type="string",
            required=True,
            description=(
                "User's eSignature REST base URI, e.g. "
                "https://demo.docusign.net/restapi — read from /oauth/userinfo "
                "after the first successful JWT exchange."
            ),
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """No-op — the node fetches a Bearer via :func:`fetch_access_token`."""
        del creds
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Exchange a JWT assertion for an access token and report the outcome."""
        try:
            async with httpx.AsyncClient(
                base_url=oauth_host_for(creds.get("environment")),
                timeout=_TEST_TIMEOUT_SECONDS,
            ) as client:
                await fetch_access_token(client, creds)
        except (httpx.HTTPError, ValueError) as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        return CredentialTestResult(ok=True, message="docusign JWT accepted")


TYPE = DocuSignJwtCredential
