"""Async repository for :class:`UserEntity`.

Handles the narrow set of user queries the Phase-2 auth flow needs:
lookup by email (login), lookup by id (JWT verification), create (bootstrap
+ registration), update (default project selection).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from weftlyflow.db.entities.user import UserEntity
from weftlyflow.db.mappers.user import user_to_domain

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.auth.views import UserView


class UserRepository:
    """Query helper around :class:`UserEntity`.

    Methods return :class:`UserView` (password-free) unless the caller
    explicitly needs the hash for verification — in which case use
    :meth:`get_entity_by_email`.
    """

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession` — one repo per request."""
        self._session = session

    async def get_by_id(self, user_id: str) -> UserView | None:
        """Return the user with ``id=user_id`` or ``None``."""
        result = await self._session.execute(select(UserEntity).where(UserEntity.id == user_id))
        entity = result.scalar_one_or_none()
        return user_to_domain(entity) if entity is not None else None

    async def get_by_email(self, email: str) -> UserView | None:
        """Return the user with ``email`` or ``None``."""
        result = await self._session.execute(
            select(UserEntity).where(UserEntity.email == email.lower()),
        )
        entity = result.scalar_one_or_none()
        return user_to_domain(entity) if entity is not None else None

    async def get_entity_by_email(self, email: str) -> UserEntity | None:
        """Return the raw entity (with ``password_hash``) for login verification."""
        result = await self._session.execute(
            select(UserEntity).where(UserEntity.email == email.lower()),
        )
        return result.scalar_one_or_none()

    async def count(self) -> int:
        """Return total number of users — used by the bootstrap check."""
        result = await self._session.execute(select(UserEntity.id))
        return len(result.scalars().all())

    async def create(
        self,
        *,
        user_id: str,
        email: str,
        password_hash: str,
        display_name: str | None,
        global_role: str,
        default_project_id: str | None = None,
    ) -> UserView:
        """Insert a new user row and return the view."""
        entity = UserEntity(
            id=user_id,
            email=email.lower(),
            password_hash=password_hash,
            display_name=display_name,
            global_role=global_role,
            default_project_id=default_project_id,
            is_active=True,
        )
        self._session.add(entity)
        await self._session.flush()
        return user_to_domain(entity)

    async def set_default_project(self, user_id: str, project_id: str) -> None:
        """Update ``default_project_id`` for an existing user."""
        entity = await self._session.get(UserEntity, user_id)
        if entity is not None:
            entity.default_project_id = project_id
