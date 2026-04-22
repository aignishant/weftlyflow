"""Utilities for composing + normalising webhook paths.

The stored representation is the canonical form: no leading slash, no
trailing slash. Ingress and registration funnels go through
:func:`normalise_path` so the lookup key matches the registered key.
"""

from __future__ import annotations

import re
from uuid import uuid4

_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._\-/]+")


def normalise_path(path: str) -> str:
    """Return ``path`` in the canonical stored form.

    Strips leading/trailing slashes and collapses any internal whitespace. Raises
    :class:`ValueError` if the remaining path is empty — webhook registration
    is useless without an addressable suffix.
    """
    cleaned = path.strip().lstrip("/").rstrip("/")
    cleaned = _SEGMENT_RE.sub("-", cleaned)
    cleaned = cleaned.strip("-")
    if not cleaned:
        msg = "webhook path must contain at least one non-whitespace segment"
        raise ValueError(msg)
    return cleaned


def static_path(workflow_id: str, node_id: str, user_path: str | None) -> str:
    """Compose a static webhook path from either user input or id-based default.

    When ``user_path`` is provided we trust it verbatim (after normalisation);
    otherwise we synthesise ``<workflow_id>/<node_id>`` so two trigger nodes
    in different workflows never collide by default.
    """
    if user_path and user_path.strip():
        return normalise_path(user_path)
    return normalise_path(f"{workflow_id}/{node_id}")


def dynamic_path() -> str:
    """Return a fresh UUID-based path suitable for a dynamic webhook."""
    return f"u/{uuid4().hex}"
