"""Scheme → provider dispatch for external secrets.

A single :class:`SecretProviderRegistry` is wired at server/worker boot
with the configured providers. Call sites hand it a reference string; the
registry parses the scheme, looks up the matching provider, and returns
the plaintext secret.
"""

from __future__ import annotations

from weftlyflow.credentials.external.base import (
    SecretProvider,
    SecretProviderError,
    parse_reference,
)


class UnknownSecretSchemeError(SecretProviderError):
    """Raised when no provider is registered for a reference's scheme."""


class SecretProviderRegistry:
    """Mutable map of ``scheme → SecretProvider``."""

    __slots__ = ("_providers",)

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._providers: dict[str, SecretProvider] = {}

    def register(self, provider: SecretProvider) -> None:
        """Register ``provider`` under its declared scheme.

        Raises:
            ValueError: If a provider for the same scheme is already
                registered. Re-registration is almost always a config
                mistake, so we fail loudly rather than silently shadowing.
        """
        scheme = provider.scheme
        if scheme in self._providers:
            msg = f"secret provider already registered for scheme {scheme!r}"
            raise ValueError(msg)
        self._providers[scheme] = provider

    def schemes(self) -> list[str]:
        """Return every registered scheme, sorted for stable output."""
        return sorted(self._providers)

    async def resolve(self, raw_reference: str) -> str:
        """Parse ``raw_reference`` and delegate to its provider.

        Raises:
            UnknownSecretSchemeError: If no provider matches the scheme.
            SecretProviderError: Anything raised by the underlying
                provider — propagated untouched so the caller can choose
                how to handle it.
        """
        reference = parse_reference(raw_reference)
        provider = self._providers.get(reference.scheme)
        if provider is None:
            msg = f"no secret provider registered for scheme {reference.scheme!r}"
            raise UnknownSecretSchemeError(msg)
        return await provider.get(reference)
