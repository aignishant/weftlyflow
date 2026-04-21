"""Authentication endpoints — login, refresh, logout, register, me.

All handlers are thin adapters. Business logic (hashing, token issuance,
revocation) lives in :mod:`weftlyflow.auth`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from weftlyflow.auth.constants import (
    PROJECT_KIND_PERSONAL,
    REFRESH_TOKEN_TYPE,
    ROLE_MEMBER,
)
from weftlyflow.auth.jwt import (
    TokenError,
    decode_token,
    hash_refresh_token,
    issue_token_pair,
)
from weftlyflow.auth.passwords import hash_password, verify_password
from weftlyflow.auth.views import UserView
from weftlyflow.config import get_settings
from weftlyflow.db.repositories.project_repo import ProjectRepository
from weftlyflow.db.repositories.refresh_token_repo import RefreshTokenRepository
from weftlyflow.db.repositories.user_repo import UserRepository
from weftlyflow.domain.ids import new_project_id, new_user_id
from weftlyflow.server.deps import get_current_user, get_db
from weftlyflow.server.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenPairResponse,
    summary="Exchange email + password for an access/refresh pair",
)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> TokenPairResponse:
    """Verify credentials and mint a token pair."""
    user_repo = UserRepository(session)
    entity = await user_repo.get_entity_by_email(body.email)
    if (
        entity is None
        or not entity.is_active
        or not verify_password(body.password, entity.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    return await _issue_tokens(
        session,
        user_id=entity.id,
        default_project_id=entity.default_project_id,
    )


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    summary="Rotate a refresh token for a fresh access/refresh pair",
)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    """Validate the refresh token, revoke it, and issue a new pair."""
    settings = get_settings()
    try:
        decoded = decode_token(
            body.refresh_token,
            secret_key=settings.secret_key.get_secret_value(),
        )
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid refresh token: {exc}",
        ) from exc
    if decoded.token_type != REFRESH_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not a refresh token",
        )
    token_hash = hash_refresh_token(body.refresh_token)
    refresh_repo = RefreshTokenRepository(session)
    entity = await refresh_repo.find_active(token_hash)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token revoked or unknown",
        )
    expires_at = entity.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token expired",
        )
    await refresh_repo.revoke_by_jti(entity.id)

    user = await UserRepository(session).get_by_id(decoded.subject)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user no longer active",
        )
    return await _issue_tokens(session, user_id=user.id, default_project_id=user.default_project_id)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke every refresh token for the current user",
)
async def logout(
    user: UserView = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Invalidate all outstanding refresh tokens for the caller."""
    await RefreshTokenRepository(session).revoke_all_for_user(user.id)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Self-service registration (gated by WEFTLYFLOW_REGISTRATION_ENABLED)",
)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user + personal project."""
    settings = get_settings()
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="self-service registration is disabled",
        )
    user_repo = UserRepository(session)
    if await user_repo.get_by_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email is already registered",
        )

    project_repo = ProjectRepository(session)
    project_id = new_project_id()
    user_id = new_user_id()
    await project_repo.create(
        project_id=project_id,
        name=body.display_name or body.email.split("@")[0],
        kind=PROJECT_KIND_PERSONAL,
        owner_id=user_id,
    )
    user = await user_repo.create(
        user_id=user_id,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        global_role=ROLE_MEMBER,
        default_project_id=project_id,
    )
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        global_role=user.global_role,
        default_project_id=user.default_project_id,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the authenticated user's profile",
)
async def me(user: UserView = Depends(get_current_user)) -> UserResponse:
    """Echo the current user (handy for JWT smoke tests + the frontend)."""
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        global_role=user.global_role,
        default_project_id=user.default_project_id,
    )


async def _issue_tokens(
    session: AsyncSession,
    *,
    user_id: str,
    default_project_id: str | None,
) -> TokenPairResponse:
    settings = get_settings()
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
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
    )
