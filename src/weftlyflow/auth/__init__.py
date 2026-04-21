"""Authentication and authorization.

Modules (populated in Phase 2):
    passwords.py : argon2id hashing + verification.
    jwt.py       : access + refresh token issue/verify.
    rbac.py      : :class:`Role`, :class:`Scope`, :func:`has_scope`.
    mfa.py       : TOTP via pyotp.
    sso/         : SAML, OIDC (Phase 6+).

See IMPLEMENTATION_BIBLE.md §16.
"""

from __future__ import annotations
