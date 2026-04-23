"""Apple App Store Connect credential — ES256 JWT signed per request.

App Store Connect
(https://developer.apple.com/documentation/appstoreconnectapi) is the
catalog's first integration that mints a fresh **ECDSA-signed**
(ES256) JWT on every outbound request. This is strictly distinct from
Ghost's HS256 (symmetric HMAC) JWT because the secret is a P-256
elliptic-curve private key distributed as a PEM/PKCS8 file, and the
signature is an ECDSA r||s byte pair — not an HMAC.

Each request carries ``Authorization: Bearer <es256_jwt>`` where the
JWT claims are:

* ``iss`` — issuer UUID from the App Store Connect portal.
* ``iat`` — current Unix time in seconds.
* ``exp`` — ``iat + 1200`` (Apple caps lifetime at 20 minutes).
* ``aud`` — ``appstoreconnect-v1`` (literal).

The header carries ``kid`` (Apple key ID, e.g. ``ABC1234XYZ``) and
``alg`` = ``ES256``.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any, ClassVar, Final

import httpx
from cryptography.exceptions import InvalidKey, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_API_HOST: Final[str] = "https://api.appstoreconnect.apple.com"
_AUDIENCE: Final[str] = "appstoreconnect-v1"
_ALGORITHM: Final[str] = "ES256"
_EXPIRY_SECONDS: Final[int] = 1200
_ECDSA_COMPONENT_BYTES: Final[int] = 32
_TEST_PATH: Final[str] = "/v1/apps?limit=1"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


def _b64url(data: bytes) -> str:
    """Base64url-encode ``data`` without padding — JWT requires stripped '='."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _load_private_key(pem: str) -> EllipticCurvePrivateKey:
    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm, InvalidKey) as exc:
        msg = f"ASC: private_key is not a valid PEM-encoded EC key: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(key, EllipticCurvePrivateKey):
        msg = "ASC: private_key must be an EC (P-256) key"
        raise ValueError(msg)
    return key


def build_asc_token(
    *,
    issuer_id: str,
    key_id: str,
    private_key_pem: str,
    now: int | None = None,
) -> str:
    """Mint a fresh ES256 JWT for App Store Connect.

    Raises:
        ValueError: If ``private_key_pem`` is unreadable or not an EC key.
    """
    key = _load_private_key(private_key_pem)
    issued_at = int(now if now is not None else time.time())
    header = {"alg": _ALGORITHM, "kid": key_id, "typ": "JWT"}
    claims = {
        "iss": issuer_id,
        "iat": issued_at,
        "exp": issued_at + _EXPIRY_SECONDS,
        "aud": _AUDIENCE,
    }
    header_seg = _b64url(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    claims_seg = _b64url(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    signing_input = f"{header_seg}.{claims_seg}".encode("ascii")
    der_signature = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der_signature)
    raw_signature = (
        r.to_bytes(_ECDSA_COMPONENT_BYTES, "big")
        + s.to_bytes(_ECDSA_COMPONENT_BYTES, "big")
    )
    return f"{header_seg}.{claims_seg}.{_b64url(raw_signature)}"


class AscApiCredential(BaseCredentialType):
    """Inject ``Authorization: Bearer <freshly-minted ES256 JWT>``."""

    slug: ClassVar[str] = "weftlyflow.asc_api"
    display_name: ClassVar[str] = "Apple App Store Connect API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://developer.apple.com/documentation/"
        "appstoreconnectapi/creating_api_keys_for_app_store_connect_api"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="issuer_id",
            display_name="Issuer ID",
            type="string",
            required=True,
            description="Issuer UUID from App Store Connect -> Users and Access -> Keys.",
        ),
        PropertySchema(
            name="key_id",
            display_name="Key ID",
            type="string",
            required=True,
            description="Key identifier (e.g. ABC1234XYZ) printed next to the .p8 download.",
        ),
        PropertySchema(
            name="private_key",
            display_name="Private Key (PEM)",
            type="string",
            required=True,
            type_options={"password": True, "rows": 12},
            description="Contents of the AuthKey_*.p8 file — a PEM-encoded P-256 EC key.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Mint a fresh ES256 JWT and attach it as a Bearer token."""
        token = build_asc_token(
            issuer_id=str(creds.get("issuer_id", "")).strip(),
            key_id=str(creds.get("key_id", "")).strip(),
            private_key_pem=str(creds.get("private_key", "")),
        )
        request.headers["Authorization"] = f"Bearer {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /v1/apps?limit=1`` and verify the JWT is accepted."""
        issuer_id = str(creds.get("issuer_id") or "").strip()
        key_id = str(creds.get("key_id") or "").strip()
        private_key = str(creds.get("private_key") or "")
        if not issuer_id or not key_id or not private_key.strip():
            return CredentialTestResult(
                ok=False,
                message="issuer_id, key_id and private_key are required",
            )
        try:
            token = build_asc_token(
                issuer_id=issuer_id, key_id=key_id, private_key_pem=private_key,
            )
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{_API_HOST}{_TEST_PATH}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"App Store Connect rejected the JWT: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="ASC JWT accepted")


TYPE = AscApiCredential
