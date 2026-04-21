"""FastAPI dependencies.

Kept intentionally tiny — a dependency should be a composition of a sub-dependency
tree and a single fetch/verify step. If logic grows, push it into a service
under the relevant subpackage and have the dependency call the service.

Planned (Phase 2):
    get_db           : async SQLAlchemy session scoped to the request.
    current_user     : JWT verification + user lookup.
    current_project  : resolve project context from header or JWT claim.
    require_scope(s) : assert the current user has a scope on a resource.
"""

from __future__ import annotations
