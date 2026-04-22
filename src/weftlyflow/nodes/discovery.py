"""Built-in and community node discovery helpers.

Kept separate from :mod:`weftlyflow.nodes.registry` so each concern is
unit-testable in isolation: the registry exercises lookup semantics with hand-
constructed fakes, the discovery module exercises package-scan edge cases.

A module is treated as declaring a node if it exposes a top-level ``NODE``
attribute whose type is a concrete subclass of one of the bases in
:mod:`weftlyflow.nodes.base`. This mirrors the convention the rest of the
codebase enforces on node packages.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from typing import TYPE_CHECKING

from weftlyflow.nodes.base import BaseNode, BasePollerNode, BaseTriggerNode

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_BUILTIN_PACKAGES: tuple[str, ...] = (
    "weftlyflow.nodes.core",
    "weftlyflow.nodes.integrations",
    "weftlyflow.nodes.ai",
)
_NODE_ATTRIBUTE: str = "NODE"
_BASE_TYPES: tuple[type, ...] = (BaseNode, BaseTriggerNode, BasePollerNode)


def iter_builtin_nodes(*, strict: bool = True) -> Iterator[type]:
    """Walk every built-in node package and yield each node class found.

    Scans ``weftlyflow.nodes.core``, ``weftlyflow.nodes.integrations``, and
    ``weftlyflow.nodes.ai`` in order so Tier-1 core nodes, Tier-2/3
    integrations, and AI nodes are all discoverable through the same entry
    point.

    Args:
        strict: Raise on import failures. When False, failing submodules are
            silently skipped so a malformed community package doesn't take
            down the whole server.
    """
    for package in _BUILTIN_PACKAGES:
        yield from _iter_nodes_under_package(package, strict=strict)


def iter_nodes_in_directory(directory: Path, *, strict: bool = False) -> Iterator[type]:
    """Import every ``*.py`` under ``directory`` and yield discovered node classes.

    The directory is added to ``sys.path`` for the duration of the scan. This
    is reserved for the community-nodes path (``WEFTLYFLOW_COMMUNITY_NODES_DIR``)
    and is intentionally a no-op Phase-1 helper beyond the sys.path hygiene.
    """
    if not directory.exists():
        if strict:
            msg = f"community nodes directory not found: {directory}"
            raise FileNotFoundError(msg)
        return
    added = str(directory) not in sys.path
    if added:
        sys.path.insert(0, str(directory))
    try:
        for py_path in sorted(directory.rglob("*.py")):
            module_name = _module_name_from_path(py_path, directory)
            yield from _safe_module_nodes(module_name, strict=strict)
    finally:
        if added:
            sys.path.remove(str(directory))


def _iter_nodes_under_package(package_name: str, *, strict: bool) -> Iterator[type]:
    try:
        package = importlib.import_module(package_name)
    except ImportError:
        if strict:
            raise
        return

    if not hasattr(package, "__path__"):
        return

    for mod_info in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
        yield from _safe_module_nodes(mod_info.name, strict=strict)


def _safe_module_nodes(module_name: str, *, strict: bool) -> Iterator[type]:
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        if strict:
            raise
        return

    candidate = getattr(module, _NODE_ATTRIBUTE, None)
    if candidate is None:
        return
    if not inspect.isclass(candidate):
        return
    if not issubclass(candidate, _BASE_TYPES):
        return
    yield candidate


def _module_name_from_path(py_path: Path, root: Path) -> str:
    relative = py_path.relative_to(root).with_suffix("")
    return ".".join(relative.parts)
