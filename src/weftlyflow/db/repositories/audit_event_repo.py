"""Async repository for :class:`AuditEventEntity`.

Two responsibilities:

* Append a row per mutating action.
* Bulk-delete rows older than a retention cut-off (called from the beat
  task in :mod:`weftlyflow.worker.tasks.audit_retention`).

The repository never updates audit rows — the audit trail is append-only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from ulid import ULID

from weftlyflow.db.entities.audit_event import AuditEventEntity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_ID_PREFIX: str = "aud_"


class AuditEventRepository:
    """Append + prune over the ``audit_events`` table."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def append(
        self,
        *,
        action: str,
        resource: str,
        actor_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEventEntity:
        """Insert one row and return the persisted entity.

        Args:
            action: Short verb-noun code — e.g. ``"workflow.create"``.
            resource: ``"<kind>:<id>"`` string. Use ``"-"`` for kinds with
                no natural id (e.g. ``"login:-"``).
            actor_id: User id of the caller, or ``None`` for anonymous
                events (failed login, webhook ingress).
            metadata: Arbitrary structured context. Encoded as JSON before
                persistence; must be JSON-serialisable.
        """
        entity = AuditEventEntity(
            id=f"{_ID_PREFIX}{ULID()}",
            actor_id=actor_id,
            action=action,
            resource=resource,
            metadata_json=json.dumps(metadata or {}, sort_keys=True, default=str),
            at=datetime.now(UTC),
        )
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def list_recent(self, *, limit: int = 100) -> list[AuditEventEntity]:
        """Return the ``limit`` most-recent rows, newest first."""
        stmt = (
            select(AuditEventEntity)
            .order_by(AuditEventEntity.at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def purge_older_than(self, retention_days: int) -> int:
        """Delete rows whose ``at`` is older than ``retention_days``.

        Args:
            retention_days: Keep-window in whole days. Must be > 0; callers
                are expected to pull this from settings.

        Returns:
            Number of rows removed.
        """
        if retention_days <= 0:
            msg = "retention_days must be positive"
            raise ValueError(msg)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self._session.execute(
            delete(AuditEventEntity).where(AuditEventEntity.at < cutoff),
        )
        return int(getattr(result, "rowcount", 0) or 0)
