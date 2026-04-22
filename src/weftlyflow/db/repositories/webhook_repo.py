"""Async repository for :class:`WebhookEntity`.

Lookup is bidirectional: ingress uses ``get_by_path_method`` (fast, project
scoping applied at the caller), while activation/deactivation uses
``list_for_workflow`` so the trigger manager can replay or tear down
registrations on workflow state changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from weftlyflow.db.entities.webhook import WebhookEntity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class WebhookRepository:
    """Read/write operations over the ``webhooks`` table."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def create(self, entity: WebhookEntity) -> WebhookEntity:
        """Persist a new webhook row and flush."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get_by_path_method(self, path: str, method: str) -> WebhookEntity | None:
        """Resolve a webhook by its unique ``(path, method)`` pair."""
        stmt = select(WebhookEntity).where(
            WebhookEntity.path == path,
            WebhookEntity.method == method,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_workflow(self, workflow_id: str) -> list[WebhookEntity]:
        """Return every webhook registered under ``workflow_id``."""
        stmt = select(WebhookEntity).where(WebhookEntity.workflow_id == workflow_id)
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def list_all(self) -> list[WebhookEntity]:
        """Return every webhook row — used by the ingress registry warm-up."""
        stmt = select(WebhookEntity)
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def delete_for_workflow(self, workflow_id: str) -> int:
        """Drop every webhook row bound to ``workflow_id``.

        Returns:
            The number of rows removed — useful for the trigger manager to
            report how many listeners were torn down.
        """
        result = await self._session.execute(
            delete(WebhookEntity).where(WebhookEntity.workflow_id == workflow_id),
        )
        return int(getattr(result, "rowcount", 0) or 0)
