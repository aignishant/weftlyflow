"""Ghost Admin credential — HS256 JWT **signed per request**.

Ghost (https://ghost.org/docs/admin-api/#token-authentication) is the
only catalog provider whose credential mints a fresh JWT on every
outbound request. The Admin API Key is printed as
``<key_id>:<secret_hex>``. The client must:

1. Build a header ``{"alg": "HS256", "typ": "JWT", "kid": key_id}``.
2. Build claims ``{"iat": now, "exp": now + 5m, "aud": "/admin/"}``.
3. Compute the signing input ``b64url(header) + '.' + b64url(claims)``.
4. HMAC-SHA256 the signing input with ``bytes.fromhex(secret_hex)``.
5. Emit ``Authorization: Ghost <header>.<claims>.<signature>``.

All primitives are stdlib — PyJWT is intentionally *not* pulled in.

The self-test calls ``GET /ghost/api/admin/site/`` which requires a
valid signed JWT and returns 200 on a valid key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, ClassVar, Final

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_AUDIENCE: Final[str] = "/admin/"
_EXPIRY_SECONDS: Final[int] = 300
_TEST_PATH: Final[str] = "/ghost/api/admin/site/"
_TEST_TIMEOUT_SECONDS: Final[float] = 10.0
_KEY_SEPARATOR: Final[str] = ":"
_EXPECTED_KEY_PARTS: Final[int] = 2


def _b64url_encode(data: bytes) -> str:
    """Base64url-encode without padding (JWT requires stripped '=' padding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_admin_token(admin_api_key: str, *, now: int | None = None) -> str:
    """Mint a fresh HS256 JWT from a Ghost Admin API key (``id:secret_hex``)."""
    parts = admin_api_key.strip().split(_KEY_SEPARATOR, maxsplit=1)
    if len(parts) != _EXPECTED_KEY_PARTS or not parts[0] or not parts[1]:
        msg = "Ghost: 'admin_api_key' must be 'id:secret_hex'"
        raise ValueError(msg)
    key_id, secret_hex = parts
    try:
        secret_bytes = bytes.fromhex(secret_hex)
    except ValueError as exc:
        msg = "Ghost: secret half of admin_api_key is not valid hex"
        raise ValueError(msg) from exc
    issued_at = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    claims = {
        "iat": issued_at,
        "exp": issued_at + _EXPIRY_SECONDS,
        "aud": _AUDIENCE,
    }
    header_segment = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    claims_segment = _b64url_encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    signing_input = f"{header_segment}.{claims_segment}".encode("ascii")
    signature = hmac.new(secret_bytes, signing_input, hashlib.sha256).digest()
    signature_segment = _b64url_encode(signature)
    return f"{header_segment}.{claims_segment}.{signature_segment}"


class GhostAdminCredential(BaseCredentialType):
    """Inject ``Authorization: Ghost <freshly-minted JWT>``."""

    slug: ClassVar[str] = "weftlyflow.ghost_admin"
    display_name: ClassVar[str] = "Ghost Admin API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://ghost.org/docs/admin-api/#token-authentication"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            required=True,
            description="Ghost site root, e.g. https://demo.ghost.io (no trailing slash).",
        ),
        PropertySchema(
            name="admin_api_key",
            display_name="Admin API Key",
            type="string",
            required=True,
            description="'<key_id>:<secret_hex>' — print from Ghost -> Integrations.",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Mint a fresh JWT and set ``Authorization: Ghost <jwt>``."""
        admin_api_key = str(creds.get("admin_api_key", "")).strip()
        token = build_admin_token(admin_api_key)
        request.headers["Authorization"] = f"Ghost {token}"
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /ghost/api/admin/site/`` and report the outcome."""
        base_url = str(creds.get("base_url") or "").strip().rstrip("/")
        admin_api_key = str(creds.get("admin_api_key") or "").strip()
        if not base_url:
            return CredentialTestResult(ok=False, message="base_url is empty")
        if not admin_api_key:
            return CredentialTestResult(ok=False, message="admin_api_key is empty")
        try:
            token = build_admin_token(admin_api_key)
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base_url}{_TEST_PATH}",
                    headers={
                        "Authorization": f"Ghost {token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"ghost rejected admin key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = GhostAdminCredential
