"""Integration tests for audit-log append + retention purge.

Uses the integration ``client`` fixture's in-memory SQLite engine so we
exercise real SQLAlchemy + real timestamps without touching Redis/Celery.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from weftlyflow.db.entities.audit_event import AuditEventEntity
from weftlyflow.db.repositories.audit_event_repo import AuditEventRepository


@pytest.mark.asyncio
async def test_append_persists_one_row(client: AsyncClient) -> None:
    session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        repo = AuditEventRepository(session)
        entity = await repo.append(
            action="workflow.create",
            resource="workflow:wf_abc",
            actor_id="usr_admin",
            metadata={"name": "Hello"},
        )
        await session.commit()
        assert entity.id.startswith("aud_")
        assert entity.metadata_json == '{"name": "Hello"}'


@pytest.mark.asyncio
async def test_list_recent_returns_newest_first(client: AsyncClient) -> None:
    session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        repo = AuditEventRepository(session)
        await repo.append(action="login", resource="login:-", actor_id="u1")
        await repo.append(action="logout", resource="login:-", actor_id="u1")
        await session.commit()

        rows = await repo.list_recent(limit=10)
        assert [r.action for r in rows] == ["logout", "login"]


@pytest.mark.asyncio
async def test_purge_older_than_deletes_only_stale(client: AsyncClient) -> None:
    session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        # Fresh row via the repo so its timestamp is "now".
        await AuditEventRepository(session).append(
            action="workflow.create",
            resource="workflow:new",
            actor_id="u1",
        )
        # Stale row inserted directly with an old ``at``.
        stale = AuditEventEntity(
            id="aud_stale0000000000000000000000",
            actor_id="u1",
            action="workflow.create",
            resource="workflow:old",
            metadata_json="{}",
            at=datetime.now(UTC) - timedelta(days=200),
        )
        session.add(stale)
        await session.commit()

        deleted = await AuditEventRepository(session).purge_older_than(90)
        await session.commit()

        assert deleted == 1
        surviving = (
            (await session.execute(select(AuditEventEntity))).scalars().all()
        )
        assert len(surviving) == 1
        assert surviving[0].resource == "workflow:new"


@pytest.mark.asyncio
async def test_purge_rejects_non_positive_retention(client: AsyncClient) -> None:
    session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        repo = AuditEventRepository(session)
        with pytest.raises(ValueError, match="positive"):
            await repo.purge_older_than(0)
