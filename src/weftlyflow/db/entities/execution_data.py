"""Execution-data rows — one-to-one with :class:`ExecutionEntity`.

``run_data`` is the serialised :class:`~weftlyflow.domain.execution.RunData`
JSON blob produced by the engine. ``workflow_snapshot`` captures the
immutable graph that was run, so reruns are deterministic even if the live
workflow has been edited since.

``storage_kind`` is a forward-looking enum (``db`` / ``fs`` / ``s3``) for the
Phase 8 binary-data offload. Phase 2 only writes ``db``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base


class ExecutionDataEntity(Base):
    """1:1 sidecar holding the serialised run-data + snapshot blob."""

    __tablename__ = "execution_data"

    execution_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("executions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workflow_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    run_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    storage_kind: Mapped[str] = mapped_column(String(8), nullable=False, default="db")
