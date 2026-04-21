"""Password hashing + verification using argon2id.

Parameters follow OWASP's 2024 cheat-sheet recommendation for argon2id. The
:class:`PasswordHasher` instance is module-global (stateless and thread-safe
per argon2-cffi's docs) so callers don't repeatedly re-tune parameters.

Nothing in this module logs the plaintext password, and no caller outside it
should either — the structlog redaction processor in
:mod:`weftlyflow.config.logging` catches most accidents, but the rule is that
raw passwords never leave an auth entry point.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

_hasher: PasswordHasher = PasswordHasher(
    time_cost=2,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    """Hash ``plaintext`` with argon2id and return the PHC-formatted string."""
    return _hasher.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True when ``plaintext`` matches ``hashed``.

    Invalid hash strings or mismatches both return False; the caller does not
    need to distinguish between them.
    """
    try:
        _hasher.verify(hashed, plaintext)
    except (VerifyMismatchError, InvalidHash):
        return False
    return True


def needs_rehash(hashed: str) -> bool:
    """Return True when ``hashed`` should be re-computed with current parameters."""
    return _hasher.check_needs_rehash(hashed)
