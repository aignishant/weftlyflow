"""SSO login + callback routes (OIDC).

Flow:

1. Browser hits ``GET /api/v1/auth/sso/oidc/login``.
2. Server mints a signed state token and 302s the browser at the IdP's
   ``authorization_endpoint`` with that token in the ``state`` query param.
3. User authenticates at the IdP; IdP redirects back to
   ``GET /api/v1/auth/sso/oidc/callback?code=...&state=...``.
4. Server verifies the state token, exchanges ``code`` for an ID token,
   verifies the ID token's signature, issuer, and audience.
5. Server finds or provisions the local user row and mints an access +
   refresh token pair.
6. Browser is redirected to :pyattr:`WeftlyflowSettings.sso_post_login_redirect`
   with the tokens attached as URL fragment parameters so nothing hits the
   server access log.

The routes are only mounted when ``sso_oidc_enabled`` is true; the app
factory validates that the four ``sso_oidc_*`` settings are populated
before registering the router.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from weftlyflow.auth.constants import (
    PROJECT_KIND_PERSONAL,
    ROLE_MEMBER,
)
from weftlyflow.auth.jwt import issue_token_pair
from weftlyflow.auth.sso.base import SSOError
from weftlyflow.auth.sso.state_token import (
    SSOStateError,
    make_state_token,
    verify_state_token,
)
from weftlyflow.config import get_settings
from weftlyflow.db.repositories.project_repo import ProjectRepository
from weftlyflow.db.repositories.refresh_token_repo import RefreshTokenRepository
from weftlyflow.db.repositories.user_repo import UserRepository
from weftlyflow.domain.ids import new_project_id, new_user_id
from weftlyflow.server.deps import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.auth.sso.base import SSOUserInfo
    from weftlyflow.auth.sso.oidc import OIDCProvider

router = APIRouter(prefix="/api/v1/auth/sso/oidc", tags=["auth", "sso"])

# SSO-only users never authenticate with a password; this sentinel fails
# :func:`verify_password` fast because it is not a valid PHC hash string.
_SSO_PASSWORD_SENTINEL: str = "!sso-only!"


@router.get("/login", summary="Redirect to the configured OIDC IdP")
async def oidc_login(request: Request) -> RedirectResponse:
    """302 the browser to the IdP's authorization endpoint."""
    provider: OIDCProvider | None = getattr(request.app.state, "sso_oidc_provider", None)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    settings = get_settings()
    await provider.prime()
    state = make_state_token(secret_key=settings.secret_key.get_secret_value())
    target = provider.authorization_url(state=state)
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


@router.get("/callback", summary="Handle the IdP redirect and mint tokens")
async def oidc_callback(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Verify state, exchange code, issue Weftlyflow tokens, redirect."""
    provider: OIDCProvider | None = getattr(request.app.state, "sso_oidc_provider", None)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    settings = get_settings()
    params = dict(request.query_params)

    raw_state = params.get("state")
    if not raw_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing state")
    try:
        verify_state_token(raw_state, secret_key=settings.secret_key.get_secret_value())
    except SSOStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid state token",
        ) from exc

    try:
        user_info = await provider.complete(params)
    except SSOError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SSO exchange failed: {exc}",
        ) from exc

    if not user_info.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IdP did not mark the user's email as verified",
        )

    user_id, default_project_id = await _find_or_provision(session, user_info)
    await session.commit()

    pair = issue_token_pair(
        user_id=user_id,
        default_project_id=default_project_id,
        secret_key=settings.secret_key.get_secret_value(),
    )
    await RefreshTokenRepository(session).create(
        jti=pair.refresh_jti,
        user_id=user_id,
        token_hash=pair.refresh_hash,
        issued_at=datetime.now(UTC),
        expires_at=pair.refresh_expires_at,
    )
    await session.commit()

    redirect_url = _build_redirect(
        base=settings.sso_post_login_redirect,
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
    )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


async def _find_or_provision(
    session: AsyncSession,
    user_info: SSOUserInfo,
) -> tuple[str, str | None]:
    """Return ``(user_id, default_project_id)`` for the SSO-authenticated user.

    Looks up by e-mail. When the user does not exist and auto-provisioning
    is enabled, creates a user + personal project in the same session; the
    caller is responsible for commit.
    """
    user_repo = UserRepository(session)
    existing_entity = await user_repo.get_entity_by_email(user_info.email)
    if existing_entity is not None:
        return existing_entity.id, existing_entity.default_project_id

    settings = get_settings()
    if not settings.sso_oidc_auto_provision:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user does not exist and SSO auto-provisioning is disabled",
        )

    project_id = new_project_id()
    user_id = new_user_id()
    await ProjectRepository(session).create(
        project_id=project_id,
        name=user_info.display_name or user_info.email.split("@")[0],
        kind=PROJECT_KIND_PERSONAL,
        owner_id=user_id,
    )
    await user_repo.create(
        user_id=user_id,
        email=user_info.email,
        password_hash=_SSO_PASSWORD_SENTINEL,
        display_name=user_info.display_name,
        global_role=ROLE_MEMBER,
        default_project_id=project_id,
    )
    return user_id, project_id


def _build_redirect(*, base: str, access_token: str, refresh_token: str) -> str:
    """Attach the tokens to ``base`` as fragment params so they never log."""
    fragment = urlencode(
        {"access_token": access_token, "refresh_token": refresh_token},
    )
    separator = "&" if "#" in base else "#"
    return f"{base}{separator}{fragment}"
