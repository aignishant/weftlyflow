"""Stateless, signed CSRF tokens for the SSO round-trip.

Problem: the browser is redirected off to the IdP and comes back minutes
later; we need to prove the callback belongs to the user who started the
flow *without* storing per-session rows in the DB.

Solution: pack ``(nonce, expiry)`` into a JSON blob, sign it with the
server's secret key (HMAC-SHA256), and send the base64url envelope as the
OIDC ``state``. On return we verify the signature and the expiry.

Why not reuse the JWT helper: the JWT module in :mod:`weftlyflow.auth.jwt`
is scoped to user access/refresh tokens with specific claim shapes. Mixing
this tiny throwaway token into that schema would muddy the validation
logic. A 30-line purpose-built token is cleaner.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from weftlyflow.auth.sso.base import SSOError

_DEFAULT_TTL: timedelta = timedelta(minutes=10)


class SSOStateError(SSOError):
    """Raised when a state token fails signature or expiry validation."""


def make_state_token(
    *,
    secret_key: str,
    ttl: timedelta | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Return a signed, short-lived state token.

    Args:
        secret_key: HMAC key — reuse the server's JWT secret so there is one
            key-rotation surface.
        ttl: How long the token is valid. Defaults to 10 minutes, which is
            generous for interactive SSO but still short.
        extra: Optional claims embedded in the payload (e.g. the post-login
            redirect URL).

    Returns:
        An opaque ``payload.signature`` string safe for URL embedding.
    """
    expires_at = datetime.now(UTC) + (ttl or _DEFAULT_TTL)
    payload: dict[str, Any] = {
        "nonce": secrets.token_urlsafe(16),
        "exp": int(expires_at.timestamp()),
    }
    if extra:
        payload.update(extra)
    payload_b = _b64encode(json.dumps(payload, sort_keys=True).encode("utf-8"))
    sig_b = _b64encode(_sign(secret_key.encode("utf-8"), payload_b))
    return f"{payload_b.decode('ascii')}.{sig_b.decode('ascii')}"


def verify_state_token(token: str, *, secret_key: str) -> dict[str, Any]:
    """Verify signature + expiry and return the embedded claims.

    Raises:
        SSOStateError: For every failure mode — malformed token, bad
            signature, expired token. The handler should respond with a
            generic 400 so callers cannot distinguish failure modes.
    """
    try:
        payload_part, sig_part = token.split(".", 1)
    except ValueError as exc:
        msg = "state token is malformed"
        raise SSOStateError(msg) from exc

    payload_b = payload_part.encode("ascii")
    expected_sig = _b64encode(_sign(secret_key.encode("utf-8"), payload_b))
    if not hmac.compare_digest(expected_sig, sig_part.encode("ascii")):
        msg = "state token signature is invalid"
        raise SSOStateError(msg)

    try:
        claims: dict[str, Any] = json.loads(_b64decode(payload_b))
    except (ValueError, UnicodeDecodeError) as exc:
        msg = "state token payload is not valid JSON"
        raise SSOStateError(msg) from exc

    exp = claims.get("exp")
    if not isinstance(exp, int) or exp < int(datetime.now(UTC).timestamp()):
        msg = "state token expired"
        raise SSOStateError(msg)
    return claims


def _sign(key: bytes, message: bytes) -> bytes:
    return hmac.new(key, message, hashlib.sha256).digest()


def _b64encode(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _b64decode(raw: bytes) -> bytes:
    # Re-pad to a multiple of four before decoding.
    pad = (-len(raw)) % 4
    return base64.urlsafe_b64decode(raw + b"=" * pad)
