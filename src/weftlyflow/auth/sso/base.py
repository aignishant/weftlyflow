"""Core types for SSO adapters.

Each adapter turns a provider-specific protocol (OIDC today; SAML tomorrow)
into a uniform two-call flow that the router layer can drive blindly:

1. ``authorization_url(state)`` — return the IdP URL to redirect the user to.
2. ``complete(callback_params)`` — exchange the callback payload for a
   normalised :class:`SSOUserInfo`.

Adapters never touch the database or the JWT layer; that bookkeeping is the
caller's job. Keeping the adapter pure makes it trivial to unit-test against
a stubbed IdP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from weftlyflow.domain.errors import WeftlyflowError


class SSOError(WeftlyflowError):
    """Base class for every failure that originates inside an SSO adapter."""


@dataclass(slots=True, frozen=True)
class SSOUserInfo:
    """Normalised profile returned after a successful IdP round-trip.

    Attributes:
        subject: Stable IdP-assigned identifier. Unique per ``(issuer,
            subject)`` tuple. Use this, not ``email``, to link the local
            user row — email can change upstream.
        email: Primary e-mail. Always lower-cased by the adapter.
        email_verified: Whether the IdP attested the email is verified.
            Weftlyflow refuses to auto-provision or auto-link users whose
            email is not verified — that would let an attacker claim an
            existing account by registering at the IdP with the same
            unverified address.
        display_name: Human-friendly name, if the IdP returned one.
        issuer: IdP issuer URL (OIDC ``iss`` claim).
    """

    subject: str
    email: str
    email_verified: bool
    issuer: str
    display_name: str | None = None


@runtime_checkable
class SSOProvider(Protocol):
    """Uniform two-call flow every SSO adapter implements."""

    name: str
    """Short identifier used in URLs — ``"oidc"`` for the built-in provider."""

    def authorization_url(self, *, state: str) -> str:
        """Return the IdP URL to redirect the browser to.

        Implementations MUST embed ``state`` in the URL exactly once so the
        callback handler can verify the round-trip belongs to the user
        who initiated it.
        """

    async def complete(self, params: dict[str, str]) -> SSOUserInfo:
        """Exchange the IdP callback query for a normalised user profile.

        Args:
            params: Flat dict of the callback query parameters — at minimum
                ``code`` and ``state``, but OIDC providers may include
                ``error``/``error_description`` too.
        """
