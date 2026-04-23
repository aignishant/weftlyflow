"""Tests for :mod:`weftlyflow.utils.redaction`."""

from __future__ import annotations

import pytest

from weftlyflow.domain.errors import (
    CredentialDecryptError,
    CredentialNotFoundError,
    CredentialTypeNotFoundError,
)
from weftlyflow.utils.redaction import safe_error_message, scrub_text


class _OtherError(Exception):
    """Plain exception class used to exercise the passthrough path."""


def test_credential_decrypt_error_is_opaque() -> None:
    exc = CredentialDecryptError("key rotation failed — stored key=abc123xyz...")
    assert safe_error_message(exc) == "credential decryption failed"


def test_credential_not_found_is_opaque() -> None:
    exc = CredentialNotFoundError("cred_01HYABC")
    assert safe_error_message(exc) == "credential not found"


def test_credential_type_not_found_is_opaque() -> None:
    exc = CredentialTypeNotFoundError("weftlyflow.unknown")
    assert safe_error_message(exc) == "credential type not registered"


@pytest.mark.parametrize(
    ("text", "expected_marker_in_output"),
    [
        ("Authorization: Bearer sk-ant-abcdef1234567890", True),
        ("connect postgres://user:password@db.host/weftlyflow", True),
        ("invalid api_key=abc123secretvalue", True),
        ("password: hunter2hunter2hunter2hunter2", True),
        ("token=eyJhbGciOiJIUzI1NiJ9.abcdef.xyz", True),
        ("plain error: something went wrong", False),
        ("value out of range", False),
    ],
)
def test_scrub_text_redacts_secret_shapes(text: str, expected_marker_in_output: bool) -> None:
    out = scrub_text(text)
    if expected_marker_in_output:
        assert "[redacted]" in out
    else:
        assert out == text


def test_safe_error_message_scrubs_unknown_exception() -> None:
    exc = _OtherError("db connect: postgres://user:supersecret@host/db failed")
    out = safe_error_message(exc)
    assert "supersecret" not in out
    assert "[redacted]" in out


def test_safe_error_message_passes_benign_exception_through() -> None:
    exc = _OtherError("index 3 out of bounds")
    assert safe_error_message(exc) == "index 3 out of bounds"
