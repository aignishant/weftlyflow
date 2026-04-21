"""Project mapper — ProjectEntity → :class:`ProjectView`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from weftlyflow.auth.views import ProjectView

if TYPE_CHECKING:
    from weftlyflow.db.entities.project import ProjectEntity


def project_to_domain(entity: ProjectEntity) -> ProjectView:
    """Return an immutable :class:`ProjectView`."""
    return ProjectView(
        id=entity.id,
        name=entity.name,
        kind=entity.kind,
        owner_id=entity.owner_id,
    )
