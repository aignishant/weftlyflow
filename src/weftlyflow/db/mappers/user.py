"""User mapper — UserEntity → opaque :class:`UserView`.

The domain layer does not have a ``User`` dataclass (users live at the
application/auth layer, not the workflow-model layer), so the "domain" side
of this mapper is a small :class:`UserView` frozen dataclass kept in
:mod:`weftlyflow.auth.views`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from weftlyflow.auth.views import UserView

if TYPE_CHECKING:
    from weftlyflow.db.entities.user import UserEntity


def user_to_domain(entity: UserEntity) -> UserView:
    """Return an immutable :class:`UserView` — omits the password hash."""
    return UserView(
        id=entity.id,
        email=entity.email,
        display_name=entity.display_name,
        global_role=entity.global_role,
        default_project_id=entity.default_project_id,
        is_active=entity.is_active,
    )
