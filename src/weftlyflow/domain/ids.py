"""ULID-based identifier generation for domain entities.

Every Weftlyflow identifier is a prefixed ULID string like ``wf_01H8...``. Prefixes
make IDs self-describing in logs and URLs without leaking to the database
(stored columns are plain strings).

Prefixes:
    wf_   workflow
    ex_   execution
    node_ node (within a workflow)
    cr_   credential
    pr_   project
    us_   user
    wh_   webhook
    tg_   tag
    vr_   variable
"""

from __future__ import annotations

from ulid import ULID


def _new(prefix: str) -> str:
    return f"{prefix}_{ULID()!s}"


def new_workflow_id() -> str:
    """Return a new ``wf_<ulid>`` identifier."""
    return _new("wf")


def new_execution_id() -> str:
    """Return a new ``ex_<ulid>`` identifier."""
    return _new("ex")


def new_node_id() -> str:
    """Return a new ``node_<ulid>`` identifier."""
    return _new("node")


def new_credential_id() -> str:
    """Return a new ``cr_<ulid>`` identifier."""
    return _new("cr")


def new_project_id() -> str:
    """Return a new ``pr_<ulid>`` identifier."""
    return _new("pr")


def new_user_id() -> str:
    """Return a new ``us_<ulid>`` identifier."""
    return _new("us")


def new_webhook_id() -> str:
    """Return a new ``wh_<ulid>`` identifier."""
    return _new("wh")
