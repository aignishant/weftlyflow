"""Database layer — SQLAlchemy 2.x entities, repositories, Alembic migrations.

Public surface:
    - :func:`weftlyflow.db.engine.get_engine` — cached sync engine.
    - :func:`weftlyflow.db.engine.get_async_engine` — cached async engine.
    - :func:`weftlyflow.db.engine.session_scope` — context-managed sync session.
    - ``Base`` in :mod:`weftlyflow.db.base` — SQLAlchemy declarative base.

Entities live in :mod:`weftlyflow.db.entities`; repositories in
:mod:`weftlyflow.db.repositories`. Both are thin translation layers — business
logic belongs in ``weftlyflow.engine`` or the relevant subpackage, not here.

Migrations are managed via Alembic with config in ``/alembic.ini``.

See IMPLEMENTATION_BIBLE.md §7.3–§7.4 for the table schema.
"""

from __future__ import annotations
