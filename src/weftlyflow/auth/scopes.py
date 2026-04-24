"""Scope-based authorization — ``has_scope(user, scope)`` helper.

Phase-2 rules: global role decides everything. Per-resource ACLs (workflow
sharing, credential sharing) arrive in Phase 6 when the ``shared_workflows``
and ``shared_credentials`` tables come online.

Role → scope mapping (per spec §16.3):

* ``owner``  → ``*`` (everything)
* ``admin``  → user + workflow + execution + credential read/write
* ``member`` → workflow + execution + credential read/write (no user mgmt)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from weftlyflow.auth.constants import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    SCOPE_CREDENTIAL_READ,
    SCOPE_CREDENTIAL_WRITE,
    SCOPE_EXECUTION_READ,
    SCOPE_EXECUTION_WRITE,
    SCOPE_USER_MANAGE,
    SCOPE_WILDCARD,
    SCOPE_WORKFLOW_EXECUTE,
    SCOPE_WORKFLOW_READ,
    SCOPE_WORKFLOW_WRITE,
)

if TYPE_CHECKING:
    from weftlyflow.auth.views import UserView

_MEMBER_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_WORKFLOW_READ,
        SCOPE_WORKFLOW_WRITE,
        SCOPE_WORKFLOW_EXECUTE,
        SCOPE_EXECUTION_READ,
        SCOPE_EXECUTION_WRITE,
        SCOPE_CREDENTIAL_READ,
        SCOPE_CREDENTIAL_WRITE,
    },
)

_ADMIN_SCOPES: frozenset[str] = _MEMBER_SCOPES | frozenset({SCOPE_USER_MANAGE})

ROLE_SCOPES: Final[dict[str, frozenset[str]]] = {
    ROLE_OWNER: frozenset({SCOPE_WILDCARD}),
    ROLE_ADMIN: _ADMIN_SCOPES,
    ROLE_MEMBER: _MEMBER_SCOPES,
}


def has_scope(user: UserView, scope: str) -> bool:
    """Return True if ``user``'s global role grants ``scope``."""
    if not user.is_active:
        return False
    granted = ROLE_SCOPES.get(user.global_role, frozenset())
    return SCOPE_WILDCARD in granted or scope in granted


def scopes_for(role: str) -> frozenset[str]:
    """Return the scope set granted by ``role`` (empty if the role is unknown)."""
    return ROLE_SCOPES.get(role, frozenset())
