"""Fernet-based encryption for credential payloads.

Credential rows never contain plaintext — the HTTP handlers encrypt on write
and decrypt on read via :class:`CredentialCipher`. Key rotation is
supported through ``MultiFernet``: set ``WEFTLYFLOW_ENCRYPTION_KEY`` to the
new key and list the old ones in ``WEFTLYFLOW_ENCRYPTION_KEY_OLD_KEYS``;
every credential will be re-encrypted under the new key on next write.

The cipher operates on ``dict[str, Any]`` payloads. We JSON-serialise the
payload before encrypting so the ciphertext is a single opaque bytes blob.
"""

from __future__ import annotations

import base64
import json
import secrets
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from weftlyflow.domain.errors import CredentialDecryptError


def generate_key() -> str:
    """Return a fresh base64-encoded 32-byte Fernet key."""
    return Fernet.generate_key().decode("utf-8")


class CredentialCipher:
    """Encrypt + decrypt credential payloads with Fernet (symmetric AES-128-CBC)."""

    __slots__ = ("_fernet",)

    def __init__(self, primary_key: str, *, old_keys: list[str] | None = None) -> None:
        """Build a :class:`MultiFernet` from the primary + any rotation keys.

        Raises:
            ValueError: when ``primary_key`` is empty or not valid base64.
        """
        if not primary_key:
            msg = "CredentialCipher requires a non-empty primary key"
            raise ValueError(msg)
        keys = [_coerce_key(primary_key)]
        for old in old_keys or []:
            if old:
                keys.append(_coerce_key(old))
        self._fernet = MultiFernet([Fernet(k) for k in keys])

    def encrypt(self, payload: dict[str, Any]) -> bytes:
        """Serialise + encrypt ``payload`` with a Fernet token."""
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(data)

    def decrypt(self, ciphertext: bytes) -> dict[str, Any]:
        """Return the plaintext payload or raise :class:`CredentialDecryptError`."""
        try:
            plain = self._fernet.decrypt(ciphertext)
        except InvalidToken as exc:
            msg = "credential failed to decrypt — rotate the key or restore the old one"
            raise CredentialDecryptError(msg) from exc
        loaded: Any = json.loads(plain.decode("utf-8"))
        if not isinstance(loaded, dict):
            msg = "credential payload is not a JSON object"
            raise CredentialDecryptError(msg)
        return loaded

    def rotate(self, ciphertext: bytes) -> bytes:
        """Re-encrypt ``ciphertext`` under the primary key — for key-rotation sweeps."""
        return self._fernet.rotate(ciphertext)


def _coerce_key(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        msg = "encryption key must be base64-encoded"
        raise ValueError(msg) from exc
    if len(raw) != _FERNET_KEY_LEN:
        msg = f"encryption key must decode to {_FERNET_KEY_LEN} bytes"
        raise ValueError(msg)
    return value.encode("utf-8")


_FERNET_KEY_LEN: int = 32


def random_nonce() -> str:
    """Return a URL-safe random nonce — used for OAuth ``state`` parameters."""
    return secrets.token_urlsafe(24)
