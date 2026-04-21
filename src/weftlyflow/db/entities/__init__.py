"""ORM entities — one class per table.

Each module declares **one** SQLAlchemy 2.x entity using the typed
``Mapped[...]`` style. Mapping from an entity row back to a domain dataclass
happens in :mod:`weftlyflow.db.mappers`, so business logic never touches an
ORM instance.

Importing this package has a side effect: every entity module registers its
table on ``Base.metadata``. Alembic's ``env.py`` imports this package so
``--autogenerate`` sees the full schema.

Phase-2 tables:
    users, projects, workflows, executions, execution_data, refresh_tokens.

Phase-4 will add ``credentials`` and ``oauth_states``. Phase-6 will add
``workflow_history`` and the sharing tables.
"""

from __future__ import annotations

from weftlyflow.db.entities.execution import ExecutionEntity
from weftlyflow.db.entities.execution_data import ExecutionDataEntity
from weftlyflow.db.entities.project import ProjectEntity
from weftlyflow.db.entities.refresh_token import RefreshTokenEntity
from weftlyflow.db.entities.user import UserEntity
from weftlyflow.db.entities.workflow import WorkflowEntity

__all__ = [
    "ExecutionDataEntity",
    "ExecutionEntity",
    "ProjectEntity",
    "RefreshTokenEntity",
    "UserEntity",
    "WorkflowEntity",
]
