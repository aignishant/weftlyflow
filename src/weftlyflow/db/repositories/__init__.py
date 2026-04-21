"""Repositories — typed query wrappers over entity classes.

Each repository takes an :class:`sqlalchemy.ext.asyncio.AsyncSession` in its
constructor and exposes high-level methods returning domain objects. This
keeps SQL/ORM concerns out of routers and executors.

Project-scoping: every query that touches a table with a ``project_id``
column requires the caller to pass one explicitly. The repository never
falls back to "no filter" — the security review in Phase 6 will verify this
invariant automatically.
"""

from __future__ import annotations

from weftlyflow.db.repositories.execution_repo import ExecutionRepository
from weftlyflow.db.repositories.project_repo import ProjectRepository
from weftlyflow.db.repositories.refresh_token_repo import RefreshTokenRepository
from weftlyflow.db.repositories.user_repo import UserRepository
from weftlyflow.db.repositories.workflow_repo import WorkflowRepository

__all__ = [
    "ExecutionRepository",
    "ProjectRepository",
    "RefreshTokenRepository",
    "UserRepository",
    "WorkflowRepository",
]
