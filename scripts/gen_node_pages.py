"""Generate one ``docs/nodes/<tier>/<slug>.md`` page per built-in Weftlyflow node.

Each node package exposes a ``NODE`` attribute whose ``spec`` is a
:class:`weftlyflow.domain.node_spec.NodeSpec`. This script walks the built-in
node tree, pulls the spec metadata and the class docstring, and emits a
user-facing reference page into ``docs/nodes/``.

Phase-0: skeleton — not yet wired into ``mkdocs.yml``. The real implementation
lands alongside the first concrete nodes in Phase 1.
"""

from __future__ import annotations


def main() -> None:
    """Placeholder — implemented in Phase 1 alongside the first node."""
    raise SystemExit("Not yet implemented. See IMPLEMENTATION_BIBLE.md §21.3.")


if __name__ == "__main__":
    main()
