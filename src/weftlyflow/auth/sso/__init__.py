"""Single Sign-On adapters.

Weftlyflow ships two built-in SSO protocols covering the common enterprise
IdPs:

* **OIDC** — Google Workspace, Microsoft Entra / Azure AD, Keycloak, Okta,
  Auth0, and any other OAuth2/OIDC-compliant IdP. Always available.
* **SAML 2.0** — ADFS, Shibboleth, legacy enterprise IdPs. Lives behind the
  ``sso`` optional-dependency group (``python3-saml``) so the default
  install stays free of ``xmlsec``'s C dependencies.

Public surface:

* :class:`SSOProvider` — protocol any adapter implements.
* :class:`SSOUserInfo` — normalised user profile returned after a
  successful login.
* :class:`OIDCProvider` — the built-in OpenID-Connect adapter.
* :func:`make_state_token` / :func:`verify_state_token` — signed, short-lived
  CSRF tokens carried through the IdP round-trip.

SAML adapter symbols (``SAMLConfig``, ``SAMLProvider``) are deliberately
**not** re-exported here — importing them eagerly would drag ``python3-saml``
into every process that touches the ``weftlyflow.auth.sso`` namespace.
Callers should ``from weftlyflow.auth.sso.saml import SAMLProvider`` on the
rare code paths that actually need SAML.
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
