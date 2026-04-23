"""Redaction helpers for error messages that cross trust boundaries.

``NodeError.message`` is persisted in ``execution_data`` and surfaced to
every user with read access on the execution. Raw exception text is
dangerous to land there because:

* ``CredentialDecryptError`` includes operator hints about key rotation;
* HTTP libraries happily echo response bodies (which may contain tokens)
  into their exception strings;
* database driver errors leak connection URLs;
* any exception subclass may override ``__str__`` to include ``self.args``
  that contain the very secret a node tried to use.

This module centralises the scrub so :class:`~weftlyflow.engine.executor.WorkflowExecutor`
and any future caller applies the same policy.

The policy is deliberately conservative: certain exception classes map to
a static, opaque string; other exceptions pass through the
:func:`scrub_text` pattern filter which drops any substring that *looks*
like a secret (long base64 blobs, ``Authorization: Bearer ...`` headers,
URLs with ``user:password@`` credentials, common secret-bearing key
names).
"""

from __future__ import annotations

import re

from weftlyflow.domain.errors import (
    CredentialDecryptError,
    CredentialNotFoundError,
    CredentialTypeNotFoundError,
)

# Exception classes that map to a fixed, non-leaking string. Operators can
# still correlate via structured logs (which carry the full trace); the
# user-visible ``NodeError.message`` gets the opaque version.
_OPAQUE_MESSAGES: dict[type[BaseException], str] = {
    CredentialDecryptError: "credential decryption failed",
    CredentialNotFoundError: "credential not found",
    CredentialTypeNotFoundError: "credential type not registered",
}

# Patterns that identify likely-secret substrings. Order does not matter —
# every match is replaced with the same redaction marker.
_REDACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # URL with embedded credentials: ``scheme://user:pass@host``
    re.compile(r"(?i)([a-z][a-z0-9+.-]*://)([^/@\s]+:[^/@\s]+)@"),
    # HTTP Authorization / Bearer headers
    re.compile(r"(?i)\b(authorization|x-api-key|x-auth-token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}"),
    # Key-like assignments (``password=abc``, ``api_key: xyz``)
    re.compile(
        r"(?i)\b(pass(?:word)?|passwd|secret|token|api[_-]?key|private[_-]?key)\s*"
        r"[:=]\s*[^\s,;}'\"]+",
    ),
    # Long base64 / hex blobs — keep the first 4 chars for debugging.
    re.compile(r"\b([A-Za-z0-9+/_=-]{32,})\b"),
)

_REDACTION_MARKER: str = "[redacted]"


def scrub_text(message: str) -> str:
    """Return ``message`` with likely-secret substrings replaced.

    This is a best-effort filter — it will miss novel secret shapes and
    may over-redact benign long tokens. Use :func:`safe_error_message`
    instead when you have a typed exception.
    """
    out = message
    for pattern in _REDACTION_PATTERNS:
        out = pattern.sub(_REDACTION_MARKER, out)
    return out


def safe_error_message(exc: BaseException) -> str:
    """Return a user-safe string for ``exc``.

    The mapping policy:

    * if ``type(exc)`` is in the opaque list, return the canned string;
    * otherwise stringify ``exc`` and run it through :func:`scrub_text`.

    The exception class name is always safe to expose via
    ``NodeError.code`` — callers should keep using ``type(exc).__name__``
    for that field.
    """
    canned = _OPAQUE_MESSAGES.get(type(exc))
    if canned is not None:
        return canned
    return scrub_text(str(exc))
