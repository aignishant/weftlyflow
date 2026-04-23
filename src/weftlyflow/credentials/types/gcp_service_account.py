"""Google Cloud service account credential — RS256 JWT Grant with scoped claim.

Google Cloud (https://developers.google.com/identity/protocols/oauth2/service-account)
accepts the standard OAuth 2.0 JWT Bearer grant, but with two claim-
shape differences from the DocuSign variant already in the catalog:

* ``aud`` is ``https://oauth2.googleapis.com/token`` — the token
  endpoint URL rather than a portal hostname.
* ``scope`` is **inside** the JWT claims (space-separated list such as
  ``https://www.googleapis.com/auth/cloud-platform``); the token
  endpoint reads it from there, not from the form body.
* No ``sub`` impersonation field is required for ordinary service-to-
  service flows (only when performing domain-wide delegation).

The node is expected to call :func:`fetch_access_token` once per
execution and reuse the Bearer returned by Google — tokens live one
hour, plenty for a single workflow run. :meth:`inject` is a no-op.
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
from weftlyflow.domain.node_spec import PropertySchema

_TOKEN_URL: Final[str] = "https://oauth2.googleapis.com/token"
_TOKEN_HOST: Final[str] = "https://oauth2.googleapis.com"
_TOKEN_PATH: Final[str] = "/token"
_GRANT_TYPE: Final[str] = "urn:ietf:params:oauth:grant-type:jwt-bearer"
_DEFAULT_SCOPE: Final[str] = "https://www.googleapis.com/auth/cloud-platform"
_JWT_EXPIRY_SECONDS: Final[int] = 3600
_TEST_TIMEOUT_SECONDS: Final[float] = 15.0


def _b64url(data: bytes) -> str:
    """Base64url-encode ``data`` without padding — required by JWT."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _load_rsa_key(pem: str) -> RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm, InvalidKey) as exc:
        msg = f"GCP: private_key is not a valid PEM-encoded RSA key: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(key, RSAPrivateKey):
        msg = "GCP: private_key must be an RSA key"
        raise ValueError(msg)
    return key


def build_jwt_assertion(
    *,
    client_email: str,
    private_key_pem: str,
    scope: str = _DEFAULT_SCOPE,
    subject: str | None = None,
    now: int | None = None,
) -> str:
    """Mint a fresh RS256 JWT ready to exchange at Google's token endpoint.

    Args:
        client_email: Service-account email — used as ``iss``.
        private_key_pem: PEM-encoded RSA key downloaded with the service account.
        scope: Space-separated OAuth scopes, encoded directly into the claim.
        subject: Only set for domain-wide delegation — the user the service
            account impersonates.
        now: Override for deterministic tests.
    """
    key = _load_rsa_key(private_key_pem)
    issued_at = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims: dict[str, Any] = {
        "iss": client_email,
        "scope": scope,
        "aud": _TOKEN_URL,
        "iat": issued_at,
        "exp": issued_at + _JWT_EXPIRY_SECONDS,
    }
    if subject:
        claims["sub"] = subject
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
    scope: str | None = None,
) -> str:
    """Mint a JWT assertion and exchange it for a Google Bearer token.

    Args:
        client: An ``httpx.AsyncClient`` whose ``base_url`` points at
            :data:`_TOKEN_HOST`.
        creds: Decrypted credential payload — must include ``client_email``
            and ``private_key``; ``scope`` and ``subject`` are optional.
        scope: Overrides the scope stored on the credential payload.

    Returns:
        The bearer access token string.

    Raises:
        ValueError: If fields are missing or Google rejects the exchange.
    """
    client_email = str(creds.get("client_email") or "").strip()
    private_key = str(creds.get("private_key") or "")
    if not client_email or not private_key.strip():
        msg = "GCP: client_email and private_key are required"
        raise ValueError(msg)
    effective_scope = (scope or str(creds.get("scope") or _DEFAULT_SCOPE)).strip()
    subject = str(creds.get("subject") or "").strip() or None
    assertion = build_jwt_assertion(
        client_email=client_email,
        private_key_pem=private_key,
        scope=effective_scope,
        subject=subject,
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
        msg = f"GCP token endpoint rejected assertion: HTTP {response.status_code}"
        raise ValueError(msg)
    try:
        payload = response.json()
    except ValueError as exc:
        msg = "GCP token endpoint returned non-JSON body"
        raise ValueError(msg) from exc
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        msg = "GCP token endpoint omitted 'access_token'"
        raise ValueError(msg)
    return token


def token_host() -> str:
    """Return the Google OAuth 2.0 token host (fixed across tenants)."""
    return _TOKEN_HOST


class GcpServiceAccountCredential(BaseCredentialType):
    """Store service-account email + RSA key — tokens are fetched at runtime."""

    slug: ClassVar[str] = "weftlyflow.gcp_service_account"
    display_name: ClassVar[str] = "Google Cloud Service Account"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developers.google.com/identity/protocols/oauth2/service-account"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="client_email",
            display_name="Service Account Email",
            type="string",
            required=True,
            description='E.g. "svc@project.iam.gserviceaccount.com" — used as JWT iss.',
        ),
        PropertySchema(
            name="private_key",
            display_name="RSA Private Key (PEM)",
            type="string",
            required=True,
            type_options={"password": True, "rows": 14},
            description="PEM-encoded RSA key from the service-account JSON file.",
        ),
        PropertySchema(
            name="scope",
            display_name="OAuth Scopes",
            type="string",
            default=_DEFAULT_SCOPE,
            description="Space-separated OAuth scopes — embedded into the JWT claim.",
        ),
        PropertySchema(
            name="subject",
            display_name="Delegated User (optional)",
            type="string",
            description="Populate only for domain-wide delegation impersonation.",
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
                base_url=_TOKEN_HOST,
                timeout=_TEST_TIMEOUT_SECONDS,
            ) as client:
                await fetch_access_token(client, creds)
        except (httpx.HTTPError, ValueError) as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        return CredentialTestResult(ok=True, message="gcp service account accepted")


TYPE = GcpServiceAccountCredential
