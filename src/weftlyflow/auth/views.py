"""Immutable view dataclasses for users and projects.

These live in the auth layer (not the pure-domain layer) because a ``User``
is an application-level concern: authentication, projects, scopes. The
domain layer stays concerned with Workflow / Execution / Item only.

Views are frozen so handlers/tests can safely pass them around without
worrying about mutation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class UserView:
    """Password-free projection of a user row.

    Attributes:
        id: ``us_<ulid>`` identifier.
        email: Login identifier — unique across all users.
        display_name: Optional human-friendly name.
        global_role: One of the role constants in :mod:`weftlyflow.auth.constants`.
        default_project_id: Used as the fallback project when no explicit
            ``X-Weftlyflow-Project`` header is supplied.
        is_active: Disabled accounts cannot log in.
    """

    id: str
    email: str
    display_name: str | None
    global_role: str
    default_project_id: str | None
    is_active: bool


@dataclass(slots=True, frozen=True)
class ProjectView:
    """Immutable projection of a project row."""

    id: str
    name: str
    kind: str
    owner_id: str
