"""Unit tests for :mod:`weftlyflow.credentials.cipher`."""

from __future__ import annotations

import pytest

from weftlyflow.credentials import CredentialCipher, generate_key
from weftlyflow.domain.errors import CredentialDecryptError


def test_round_trip_payload() -> None:
    cipher = CredentialCipher(generate_key())
    payload = {"token": "xyz", "scope": "read"}
    ct = cipher.encrypt(payload)
    assert ct != payload
    assert cipher.decrypt(ct) == payload


def test_rotation_decrypts_ciphertext_from_old_key() -> None:
    old_key = generate_key()
    new_key = generate_key()
    old_cipher = CredentialCipher(old_key)
    token = old_cipher.encrypt({"secret": "value"})

    # New instance: primary = new_key, allow fallback to old_key.
    rotated = CredentialCipher(new_key, old_keys=[old_key])
    assert rotated.decrypt(token) == {"secret": "value"}
    # And we can re-wrap under the new key.
    re_wrapped = rotated.rotate(token)
    assert CredentialCipher(new_key).decrypt(re_wrapped) == {"secret": "value"}


def test_garbage_token_raises_decrypt_error() -> None:
    cipher = CredentialCipher(generate_key())
    with pytest.raises(CredentialDecryptError):
        cipher.decrypt(b"not a real token")


def test_non_object_payload_raises_decrypt_error() -> None:
    # Build a valid Fernet token containing a JSON array so decrypt reaches
    # the "not a dict" branch.
    import json

    from cryptography.fernet import Fernet

    key = generate_key()
    cipher = CredentialCipher(key)
    token = Fernet(key.encode("utf-8")).encrypt(json.dumps([1, 2, 3]).encode("utf-8"))
    with pytest.raises(CredentialDecryptError):
        cipher.decrypt(token)


def test_empty_primary_key_raises() -> None:
    with pytest.raises(ValueError):
        CredentialCipher("")


def test_invalid_base64_primary_key_raises() -> None:
    with pytest.raises(ValueError):
        CredentialCipher("not-base64!!")
