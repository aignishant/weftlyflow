"""Auth layer constants — scope names, token-type tokens, time intervals.

Centralising these avoids magic strings scattered across routers, deps, and
the JWT helpers. Adding a new scope? It must appear here and nowhere else.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

# --- JWT token kinds ---
ACCESS_TOKEN_TYPE: Final[str] = "access"
REFRESH_TOKEN_TYPE: Final[str] = "refresh"

ACCESS_TOKEN_TTL: Final[timedelta] = timedelta(minutes=15)
REFRESH_TOKEN_TTL: Final[timedelta] = timedelta(days=14)

JWT_ALGORITHM: Final[str] = "HS256"

# --- Global roles (spec §16.3) ---
ROLE_OWNER: Final[str] = "owner"
ROLE_ADMIN: Final[str] = "admin"
ROLE_MEMBER: Final[str] = "member"

GLOBAL_ROLES: Final[frozenset[str]] = frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER})

# --- Scopes ---
SCOPE_WORKFLOW_READ: Final[str] = "workflow:read"
SCOPE_WORKFLOW_WRITE: Final[str] = "workflow:write"
SCOPE_WORKFLOW_EXECUTE: Final[str] = "workflow:execute"
SCOPE_EXECUTION_READ: Final[str] = "execution:read"
SCOPE_EXECUTION_WRITE: Final[str] = "execution:write"
SCOPE_CREDENTIAL_READ: Final[str] = "credential:read"
SCOPE_CREDENTIAL_WRITE: Final[str] = "credential:write"
SCOPE_USER_MANAGE: Final[str] = "user:manage"
SCOPE_WILDCARD: Final[str] = "*"

# --- Project kinds ---
PROJECT_KIND_PERSONAL: Final[str] = "personal"
PROJECT_KIND_TEAM: Final[str] = "team"

# --- Header names ---
PROJECT_HEADER: Final[str] = "X-Weftlyflow-Project"
REQUEST_ID_HEADER: Final[str] = "X-Request-Id"
