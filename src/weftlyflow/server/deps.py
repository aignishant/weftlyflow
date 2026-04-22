"""FastAPI dependencies — session, auth, project scope, node registry.

Dependencies are cheap, reusable, and typed. Routers declare what they need
via ``Depends(...)`` and never reach into ``app.state`` directly.

Lifecycle:

* :func:`get_db` — one :class:`AsyncSession` per request, auto-commits on
  success and rolls back on exception.
* :func:`get_current_user` — decodes the JWT, loads the user from the DB,
  asserts active.
* :func:`get_current_project` — resolves the effective project id from the
  JWT default + optional ``X-Weftlyflow-Project`` override.
* :func:`require_scope` — factory that produces a scope-guard dependency.
* :func:`get_registry` — shared :class:`NodeRegistry` loaded at startup.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from weftlyflow.auth.constants import (
    ACCESS_TOKEN_TYPE,
    PROJECT_HEADER,
    SCOPE_WILDCARD,
)
from weftlyflow.auth.jwt import TokenError, decode_token
from weftlyflow.auth.scopes import has_scope
from weftlyflow.auth.views import UserView
from weftlyflow.config import get_settings
from weftlyflow.db.repositories.project_repo import ProjectRepository
from weftlyflow.db.repositories.user_repo import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.nodes.registry import NodeRegistry
    from weftlyflow.triggers.manager import ActiveTriggerManager
    from weftlyflow.webhooks.registry import WebhookRegistry
    from weftlyflow.worker.queue import ExecutionQueue

_bearer = HTTPBearer(auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield an :class:`AsyncSession` bound to this request.

    Commits on clean exit, rolls back otherwise. The session factory is
    provided by the lifespan on ``app.state.session_factory``.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_registry(request: Request) -> NodeRegistry:
    """Return the shared :class:`NodeRegistry` wired at startup."""
    registry: NodeRegistry = request.app.state.node_registry
    return registry


def get_webhook_registry(request: Request) -> WebhookRegistry:
    """Return the shared :class:`WebhookRegistry` wired at startup."""
    registry: WebhookRegistry = request.app.state.webhook_registry
    return registry


def get_execution_queue(request: Request) -> ExecutionQueue:
    """Return the shared :class:`ExecutionQueue` wired at startup."""
    queue: ExecutionQueue = request.app.state.execution_queue
    return queue


def get_trigger_manager(request: Request) -> ActiveTriggerManager:
    """Return the shared :class:`ActiveTriggerManager` wired at startup."""
    manager: ActiveTriggerManager = request.app.state.trigger_manager
    return manager


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> UserView:
    """Resolve the authenticated user from a bearer access token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    try:
        decoded = decode_token(
            credentials.credentials,
            secret_key=settings.secret_key.get_secret_value(),
        )
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if decoded.token_type != ACCESS_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh tokens may not be used as access tokens",
        )
    user = await UserRepository(session).get_by_id(decoded.subject)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


async def get_current_project(
    project_override: str | None = Header(default=None, alias=PROJECT_HEADER),
    user: UserView = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> str:
    """Resolve the effective project id for the current request.

    Header override (``X-Weftlyflow-Project``) wins if supplied and the user
    has access to it; otherwise falls back to the user's default project.
    """
    candidate = project_override or user.default_project_id
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no project selected for this request",
        )
    project = await ProjectRepository(session).get_by_id(candidate)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"project {candidate!r} not found",
        )
    if project.owner_id != user.id and user.global_role != "owner":
        # Phase 6 will extend this with shared_* membership checks.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you do not have access to this project",
        )
    return project.id


def require_scope(scope: str) -> Callable[[UserView], Awaitable[UserView]]:
    """Return a dependency that enforces ``scope`` on the current user."""

    async def _dep(user: UserView = Depends(get_current_user)) -> UserView:
        if not has_scope(user, scope) and scope != SCOPE_WILDCARD:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing scope: {scope}",
            )
        return user

    return _dep
