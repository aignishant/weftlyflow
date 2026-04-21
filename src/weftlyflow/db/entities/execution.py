"""Executions — metadata row for one workflow run.

The bulky ``run_data`` blob lives in :class:`ExecutionDataEntity` (a separate
table) so listing + filtering on executions does not pay the cost of
serialising per-node outputs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin


class ExecutionEntity(Base, IdMixin):
    """Run metadata — status, timing, mode, the originating trigger."""

    __tablename__ = "executions"

    workflow_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wait_till: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
