"""Auth DTOs — login, refresh, register, and the user-view response body."""

from __future__ import annotations

from pydantic import EmailStr, Field

from weftlyflow.server.schemas.common import WeftlyflowModel


class LoginRequest(WeftlyflowModel):
    """Body for ``POST /api/v1/auth/login``."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(WeftlyflowModel):
    """Body for ``POST /api/v1/auth/refresh``."""

    refresh_token: str = Field(min_length=1)


class RegisterRequest(WeftlyflowModel):
    """Body for ``POST /api/v1/auth/register``."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)


class TokenPairResponse(WeftlyflowModel):
    """Response shape for login + refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(WeftlyflowModel):
    """Current-user projection returned by ``/api/v1/auth/me``."""

    id: str
    email: EmailStr
    display_name: str | None = None
    global_role: str
    default_project_id: str | None = None
