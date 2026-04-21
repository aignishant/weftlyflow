"""Node registry — discovery, versioning, lookup.

Nodes are keyed by ``(spec.type, spec.version)``. A registry is populated at
process start (via :func:`NodeRegistry.load_builtins` and, eventually,
entry points + community directory loaders in later phases) and treated as
read-only thereafter.

The registry is not a singleton. Tests construct fresh registries freely; the
server/worker each build one at boot and inject it into the executor.

See IMPLEMENTATION_BIBLE.md §9.4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from weftlyflow.domain.node_spec import NodeSpec
from weftlyflow.nodes.base import BaseNode, BasePollerNode, BaseTriggerNode

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

_NodeClass = type[BaseNode] | type[BaseTriggerNode] | type[BasePollerNode]


class NodeRegistryError(Exception):
    """Raised for registry-level misuse (duplicate registration, unknown type)."""


class NodeRegistry:
    """In-memory registry of node classes keyed by ``(type, version)``.

    Example:
        >>> registry = NodeRegistry()
        >>> registry.register(MyNode)
        >>> cls = registry.get("weftlyflow.my_node", 1)
    """

    __slots__ = ("_by_key", "_latest_version")

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._by_key: dict[tuple[str, int], _NodeClass] = {}
        self._latest_version: dict[str, int] = {}

    def register(self, node_cls: _NodeClass, *, replace: bool = False) -> _NodeClass:
        """Register ``node_cls`` keyed by ``(spec.type, spec.version)``.

        Args:
            node_cls: The node implementation class. Must declare a ``spec``
                :class:`NodeSpec` class attribute.
            replace: Overwrite an existing registration. Default is False to
                catch accidental double-registration.

        Returns:
            The registered class, unchanged — so ``@registry.register`` can be
            used as a decorator.

        Raises:
            NodeRegistryError: when ``spec`` is missing, malformed, or when
                ``(type, version)`` already exists and ``replace`` is False.
        """
        spec = _spec_of(node_cls)
        key = (spec.type, spec.version)
        if key in self._by_key and not replace:
            msg = f"node already registered: {spec.type} v{spec.version}"
            raise NodeRegistryError(msg)
        self._by_key[key] = node_cls
        latest = self._latest_version.get(spec.type, 0)
        if spec.version > latest:
            self._latest_version[spec.type] = spec.version
        return node_cls

    def get(self, node_type: str, version: int) -> _NodeClass:
        """Return the registered class for ``(type, version)``.

        Raises:
            KeyError: when the key is not registered.
        """
        return self._by_key[(node_type, version)]

    def latest(self, node_type: str) -> _NodeClass:
        """Return the highest-versioned class registered under ``type``."""
        if node_type not in self._latest_version:
            msg = f"no node registered with type {node_type!r}"
            raise NodeRegistryError(msg)
        return self._by_key[(node_type, self._latest_version[node_type])]

    def catalog(self) -> list[NodeSpec]:
        """Return every registered spec — useful for the ``GET /node-types`` endpoint."""
        return [_spec_of(cls) for cls in self._by_key.values()]

    def __contains__(self, key: object) -> bool:
        """Support ``("type", 1) in registry`` membership checks."""
        return isinstance(key, tuple) and key in self._by_key

    def __len__(self) -> int:
        """Number of registered ``(type, version)`` pairs."""
        return len(self._by_key)

    def load_builtins(self, *, strict: bool = True) -> int:
        """Import every ``core``-tier built-in and register its ``NODE``.

        Args:
            strict: When True (default), a missing or malformed built-in raises.
                When False, bad modules are skipped silently — useful for
                partial installs.

        Returns:
            Number of newly-registered node classes.
        """
        from weftlyflow.nodes import discovery  # noqa: PLC0415 — lazy to keep imports light.

        before = len(self)
        for node_cls in discovery.iter_builtin_nodes(strict=strict):
            self.register(node_cls)
        return len(self) - before

    def load_from_directory(self, directory: Path, *, strict: bool = False) -> int:
        """Import every Python module under ``directory`` and register discovered nodes.

        Reserved for the community-nodes path (``WEFTLYFLOW_COMMUNITY_NODES_DIR``).
        Not wired to runtime yet — parameter kept so the signature is stable.
        """
        from weftlyflow.nodes import discovery  # noqa: PLC0415

        before = len(self)
        for node_cls in discovery.iter_nodes_in_directory(directory, strict=strict):
            self.register(node_cls)
        return len(self) - before

    def register_many(self, classes: Iterable[_NodeClass], *, replace: bool = False) -> None:
        """Bulk register — convenience for test fixtures."""
        for cls in classes:
            self.register(cls, replace=replace)


def register_node(registry: NodeRegistry) -> Callable[[_NodeClass], _NodeClass]:
    """Return a decorator that registers the decorated class on ``registry``.

    Example:
        >>> registry = NodeRegistry()
        >>> @register_node(registry)
        ... class MyNode(BaseNode):
        ...     spec = NodeSpec(...)
        ...     async def execute(self, ctx, items): return [items]
    """

    def _decorator(cls: _NodeClass) -> _NodeClass:
        registry.register(cls)
        return cls

    return _decorator


def _spec_of(node_cls: _NodeClass) -> NodeSpec:
    spec = getattr(node_cls, "spec", None)
    if not isinstance(spec, NodeSpec):
        msg = f"{node_cls.__qualname__} is missing a NodeSpec class attribute"
        raise NodeRegistryError(msg)
    return spec
