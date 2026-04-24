"""Execution-data rows — one-to-one with :class:`ExecutionEntity`.

``run_data`` is the serialised :class:`~weftlyflow.domain.execution.RunData`
JSON blob produced by the engine. ``workflow_snapshot`` captures the
immutable graph that was run, so reruns are deterministic even if the live
workflow has been edited since.

``storage_kind`` selects the backend that actually holds the payload
(``db`` / ``fs`` / ``s3``). For ``db`` the two JSON columns are authoritative;
for anything else those columns are empty ``{}`` and ``external_ref`` points
at the blob in whatever storage the
:class:`~weftlyflow.db.execution_storage.ExecutionDataStore` owns.
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
    external_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
