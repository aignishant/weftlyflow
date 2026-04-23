"""Single Sign-On adapters.

Weftlyflow ships with one built-in SSO protocol — **OIDC** — covering the
common enterprise IdPs (Google Workspace, Microsoft Entra / Azure AD,
Keycloak, Okta, Auth0). SAML is intentionally left to a future phase and
lives behind the ``sso`` optional-dependency group (``python3-saml``).

Public surface:

* :class:`SSOProvider` — protocol any adapter implements.
* :class:`SSOUserInfo` — normalised user profile returned after a
  successful login.
* :class:`OIDCProvider` — the built-in OpenID-Connect adapter.
* :func:`make_state_token` / :func:`verify_state_token` — signed, short-lived
  CSRF tokens carried through the IdP round-trip.
"""

from __future__ import annotations

from weftlyflow.auth.sso.base import SSOError, SSOProvider, SSOUserInfo
from weftlyflow.auth.sso.oidc import OIDCProvider
from weftlyflow.auth.sso.state_token import (
    SSOStateError,
    make_state_token,
    verify_state_token,
)

__all__ = [
    "OIDCProvider",
    "SSOError",
    "SSOProvider",
    "SSOStateError",
    "SSOUserInfo",
    "make_state_token",
    "verify_state_token",
]
