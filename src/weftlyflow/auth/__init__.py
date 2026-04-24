"""Authentication + authorization subsystem.

Public surface:
    * :mod:`weftlyflow.auth.passwords` — argon2id hash + verify.
    * :mod:`weftlyflow.auth.jwt` — access + refresh token issuance.
    * :mod:`weftlyflow.auth.scopes` — role → scope mapping + ``has_scope``.
    * :mod:`weftlyflow.auth.bootstrap` — first-run admin + project seed.
    * :class:`UserView`, :class:`ProjectView` — immutable projections used
      everywhere the server layer needs a user/project reference.

See weftlyinfo.md §16.
"""

from __future__ import annotations

from weftlyflow.auth.jwt import (
    DecodedToken,
    TokenError,
    TokenPair,
    decode_token,
    hash_refresh_token,
    issue_token_pair,
)
from weftlyflow.auth.passwords import hash_password, needs_rehash, verify_password
from weftlyflow.auth.scopes import has_scope, scopes_for
from weftlyflow.auth.views import ProjectView, UserView

__all__ = [
    "DecodedToken",
    "ProjectView",
    "TokenError",
    "TokenPair",
    "UserView",
    "decode_token",
    "has_scope",
    "hash_password",
    "hash_refresh_token",
    "issue_token_pair",
    "needs_rehash",
    "scopes_for",
    "verify_password",
]
