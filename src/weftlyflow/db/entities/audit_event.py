"""Audit-event rows — the append-only trail of mutating actions.

Every write path the server accepts — login, workflow create, credential
delete, permission change — appends one row here. Rows are never updated.
A background beat task (:mod:`weftlyflow.worker.tasks.audit_retention`)
prunes entries older than ``settings.audit_retention_days``.

Schema notes:

* ``actor_id`` is nullable so unauthenticated events (failed login, webhook
  ingress) still record cleanly — otherwise we would need a sentinel user.
* ``resource`` captures ``"<kind>:<id>"`` — e.g. ``"workflow:wf_abc"``. The
  writer chooses the format; this column is an opaque string as far as
  SQLAlchemy is concerned.
* ``metadata_json`` is the structured detail blob. Kept as TEXT-encoded
  JSON because SQLite is one of our supported backends and JSONB is not
  portable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin, _utcnow


class AuditEventEntity(Base, IdMixin):
    """One immutable audit row."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_at", "at"),
        Index("ix_audit_events_actor_at", "actor_id", "at"),
    )

    actor_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource: Mapped[str] = mapped_column(String(120), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
