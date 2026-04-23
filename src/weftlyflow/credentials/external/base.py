"""Core types for external-secret providers.

Two concepts:

* :class:`SecretReference` — a parsed ``"<scheme>:<path>"`` pair with an
  optional ``#fragment`` selecting a field within a structured secret.
* :class:`SecretProvider` — an async protocol every backend implements.

Reference string grammar (clean-room; does not mirror any specific vendor):

.. code-block:: text

    <reference> ::= <scheme> ":" <path> [ "#" <field> ]
    <scheme>    ::= [a-z][a-z0-9_-]*
    <path>      ::= non-empty, scheme-specific

Example references:

* ``env:SLACK_BOT_TOKEN``              — environment variable
* ``env:AWS_SECRET_ACCESS_KEY``
* ``vault:kv/data/slack#token``        — Vault KV v2, field ``token`` (future impl)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from weftlyflow.domain.errors import WeftlyflowError


class SecretProviderError(WeftlyflowError):
    """Base class for everything that can go wrong inside a provider."""


class SecretNotFoundError(SecretProviderError):
    """Raised when the provider cannot locate the referenced secret."""


class MalformedSecretReferenceError(SecretProviderError):
    """Raised when a reference string is not ``scheme:path[#field]``."""


@dataclass(slots=True, frozen=True)
class SecretReference:
    """Parsed view of a ``scheme:path[#field]`` reference string.

    Attributes:
        scheme: Lower-case provider identifier (e.g. ``"env"``, ``"vault"``).
        path: Provider-specific locator. Opaque to this module; each
            provider decides how to interpret it.
        field: Optional structured-secret key, populated when the reference
            had a ``#field`` fragment.
    """

    scheme: str
    path: str
    field: str | None = None

    @property
    def raw(self) -> str:
        """Return the canonical ``scheme:path[#field]`` string."""
        if self.field is None:
            return f"{self.scheme}:{self.path}"
        return f"{self.scheme}:{self.path}#{self.field}"


def parse_reference(raw: str) -> SecretReference:
    """Parse a reference string into a :class:`SecretReference`.

    Args:
        raw: Input in ``scheme:path[#field]`` form.

    Returns:
        A :class:`SecretReference`.

    Raises:
        MalformedSecretReferenceError: If the input has no scheme, an empty
            path, or malformed separators.

    Example:
        >>> parse_reference("env:SLACK_TOKEN")
        SecretReference(scheme='env', path='SLACK_TOKEN', field=None)
        >>> parse_reference("vault:kv/data/slack#token").field
        'token'
    """
    if not raw or ":" not in raw:
        msg = f"secret reference must be scheme:path, got {raw!r}"
        raise MalformedSecretReferenceError(msg)
    scheme, _, remainder = raw.partition(":")
    scheme = scheme.strip().lower()
    if not scheme:
        msg = f"secret reference has empty scheme: {raw!r}"
        raise MalformedSecretReferenceError(msg)
    if not remainder:
        msg = f"secret reference has empty path: {raw!r}"
        raise MalformedSecretReferenceError(msg)
    path, sep, field = remainder.partition("#")
    if not path:
        msg = f"secret reference has empty path: {raw!r}"
        raise MalformedSecretReferenceError(msg)
    return SecretReference(scheme=scheme, path=path, field=field if sep else None)


@runtime_checkable
class SecretProvider(Protocol):
    """Contract every external-secret backend must implement.

    A provider is bound to a single scheme (``env``, ``vault``, ...) and
    returns the plaintext secret for any reference that carries its
    scheme. Implementations SHOULD be idempotent and safe to call from
    multiple coroutines.
    """

    scheme: str

    async def get(self, reference: SecretReference) -> str:
        """Return the plaintext secret for ``reference``.

        Raises:
            SecretNotFoundError: The secret does not exist in this backend.
            SecretProviderError: Any other backend-specific failure
                (network, auth, parse). Callers should treat both subclasses
                as opaque and never leak the raw message to end users.
        """
