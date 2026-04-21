"""Node registry — discovery, versioning, lookup.

Nodes are keyed by ``(spec.type, spec.version)``. The registry is populated at
process start and is read-only thereafter.

Implementation plan (Phase 1):
    - :class:`NodeRegistry` with ``register()``, ``get()``, ``get_catalog()``.
    - :func:`load_builtins` — scan :mod:`weftlyflow.nodes.core` and subpackages.
    - :func:`load_entry_points` — ``weftlyflow.nodes`` setuptools entry points.
    - :func:`load_from_dir` — optional community nodes directory.

See IMPLEMENTATION_BIBLE.md §9.4.
"""

from __future__ import annotations
