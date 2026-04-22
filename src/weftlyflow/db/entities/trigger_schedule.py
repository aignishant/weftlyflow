"""Trigger schedules — persisted cron/interval registrations for a workflow node.

When a workflow containing a ``weftlyflow.schedule_trigger`` is activated, the
trigger manager writes one row per trigger node here. On process restart the
leader instance replays these rows into APScheduler so schedules survive
across deployments.

This table intentionally mirrors the structure of ``webhooks`` — both are
"active trigger" tables that the leader owns. We keep them separate so the
unique constraint on webhook ``(path, method)`` is not entangled with the
schedule domain.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin, TimestampMixin


class TriggerScheduleEntity(Base, IdMixin, TimestampMixin):
    """Active-schedule row — one per ``schedule_trigger`` node in an active workflow."""

    __tablename__ = "trigger_schedules"

    workflow_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(40), nullable=False)
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String(120), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
