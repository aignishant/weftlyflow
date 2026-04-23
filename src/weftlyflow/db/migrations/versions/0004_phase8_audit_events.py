"""Phase-8 schema — audit_events.

Revision ID: 0004_phase8_audit_events
Revises: 0003_phase4_credentials
Create Date: 2026-04-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase8_audit_events"
down_revision: str | None = "0003_phase4_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the append-only audit_events table."""
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("actor_id", sa.String(length=40), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource", sa.String(length=120), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_at", "audit_events", ["at"])
    op.create_index("ix_audit_events_actor_at", "audit_events", ["actor_id", "at"])


def downgrade() -> None:
    """Drop the audit_events table."""
    op.drop_index("ix_audit_events_actor_at", table_name="audit_events")
    op.drop_index("ix_audit_events_at", table_name="audit_events")
    op.drop_table("audit_events")
