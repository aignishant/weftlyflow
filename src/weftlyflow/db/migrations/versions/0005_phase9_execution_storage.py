"""Phase-9 schema — execution_data.external_ref.

Adds the ``external_ref`` column so pluggable execution-data storage backends
(filesystem, S3) can point at their blob without abusing the JSON columns.

Revision ID: 0005_phase9_execution_storage
Revises: 0004_phase8_audit_events
Create Date: 2026-04-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase9_execution_storage"
down_revision: str | None = "0004_phase8_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``external_ref`` as a nullable string column."""
    with op.batch_alter_table("execution_data") as batch:
        batch.add_column(sa.Column("external_ref", sa.String(length=512), nullable=True))


def downgrade() -> None:
    """Drop ``external_ref``."""
    with op.batch_alter_table("execution_data") as batch:
        batch.drop_column("external_ref")
