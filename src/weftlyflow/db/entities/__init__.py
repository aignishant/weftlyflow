"""ORM entities — one class per table.

Each module under this package defines **one** SQLAlchemy 2.x entity using the
typed ``Mapped[...]`` style. These classes are mirrors of the domain
dataclasses in :mod:`weftlyflow.domain`; the mapping from entity row to domain
object lives in :mod:`weftlyflow.db.mappers` (added in Phase 2).

No cross-entity business logic belongs in this package — write a repository.

Implementation plan (Phase 2):
    - workflow.py, workflow_history.py
    - execution.py, execution_data.py
    - credential.py
    - user.py, refresh_token.py
    - project.py, shared_workflow.py, shared_credential.py
    - webhook.py
    - tag.py, variable.py
    - audit_event.py, oauth_state.py, binary_data_file.py
"""

from __future__ import annotations
