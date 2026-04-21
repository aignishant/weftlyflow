"""Alembic migration package.

Versions live under ``versions/``. Generate a new revision with::

    make db-revision MSG="add-webhook-table"
    # or:
    alembic revision --autogenerate -m "add-webhook-table"

Apply::

    make db-upgrade

Roll back one::

    make db-downgrade
"""

from __future__ import annotations
