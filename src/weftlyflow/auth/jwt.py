"""JWT encode/decode helpers for access and refresh tokens.

Tokens are HS256-signed with ``settings.secret_key``. Claims shape::

    {
        "sub": "<user_id>",
        "typ": "access" | "refresh",
        "pid": "<default_project_id>"  # optional, access tokens only
        "iat": <unix ts>,
        "exp": <unix ts>,
        "jti": "<ulid>"                # unique per token, used for revocation
    }

Refresh-token rotation works by:
1. verifying the presented refresh token,
2. deleting its row from ``refresh_tokens`` (by ``jti``),
3. issuing a fresh pair.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from ulid import ULID

from weftlyflow.auth.constants import (
    ACCESS_TOKEN_TTL,
    ACCESS_TOKEN_TYPE,
    JWT_ALGORITHM,
    REFRESH_TOKEN_TTL,
    REFRESH_TOKEN_TYPE,
)


@dataclass(slots=True, frozen=True)
class TokenPair:
    """Return shape from :func:`issue_token_pair`."""

    access_token: str
    refresh_token: str
    refresh_jti: str
    refresh_hash: str
    refresh_expires_at: datetime


@dataclass(slots=True, frozen=True)
class DecodedToken:
    """Validated claims returned by :func:`decode_token`."""

    subject: str
    token_type: str
    default_project_id: str | None
    jti: str
    issued_at: datetime
    expires_at: datetime


class TokenError(Exception):
    """Raised for any JWT validation failure."""


def issue_token_pair(
    *,
    user_id: str,
    default_project_id: str | None,
    secret_key: str,
    now: datetime | None = None,
) -> TokenPair:
    """Mint a new access + refresh token pair and return the hash for persistence."""
    issued = now or datetime.now(UTC)
    access = _encode(
        subject=user_id,
        token_type=ACCESS_TOKEN_TYPE,
        ttl=ACCESS_TOKEN_TTL,
        secret_key=secret_key,
        issued_at=issued,
        default_project_id=default_project_id,
    )
    refresh_jti = str(ULID())
    refresh_token = _encode(
        subject=user_id,
        token_type=REFRESH_TOKEN_TYPE,
        ttl=REFRESH_TOKEN_TTL,
        secret_key=secret_key,
        issued_at=issued,
        jti=refresh_jti,
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh_token,
        refresh_jti=refresh_jti,
        refresh_hash=hash_refresh_token(refresh_token),
        refresh_expires_at=issued + REFRESH_TOKEN_TTL,
    )


def decode_token(token: str, *, secret_key: str) -> DecodedToken:
    """Verify signature + expiry and return the validated claims.

    Raises:
        TokenError: on invalid signature, expired token, or missing claims.
    """
    try:
        payload: dict[str, Any] = jwt.decode(token, secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    try:
        return DecodedToken(
            subject=str(payload["sub"]),
            token_type=str(payload["typ"]),
            default_project_id=payload.get("pid"),
            jti=str(payload.get("jti", "")),
            issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
    except (KeyError, ValueError) as exc:
        msg = "token is missing required claims"
        raise TokenError(msg) from exc


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 hex digest used as the ``refresh_tokens.token_hash`` value."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _encode(
    *,
    subject: str,
    token_type: str,
    ttl: timedelta,
    secret_key: str,
    issued_at: datetime,
    default_project_id: str | None = None,
    jti: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + ttl).timestamp()),
        "jti": jti or str(ULID()),
    }
    if default_project_id is not None:
        payload["pid"] = default_project_id
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)
