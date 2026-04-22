"""In-process webhook route table backed by the database.

The registry is the single source of truth for ``(path, method) ->
WebhookEntry`` lookups during an HTTP request. It is populated two ways:

* **Warm-up on boot** — :meth:`load_from_database` replays every row in the
  ``webhooks`` table. Every API instance does this, so no single-point-of-
  failure on the leader.
* **Live updates** — :meth:`register` / :meth:`unregister` keep the table
  consistent when the trigger manager activates or deactivates a workflow.
  In a multi-instance deploy Phase 4 will broadcast these via Redis
  pub/sub; Phase 3 only guarantees consistency within one process.

The registry is deliberately thread-safe via a single lock: the set of
registered webhooks is small (hundreds, not millions) so coarse locking is
both correct and fast enough.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from weftlyflow.webhooks.constants import SUPPORTED_METHODS
from weftlyflow.webhooks.paths import normalise_path
from weftlyflow.webhooks.types import WebhookEntry

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weftlyflow.db.entities.webhook import WebhookEntity


class WebhookConflictError(Exception):
    """Raised when a registration would shadow an existing ``(path, method)``."""


class UnsupportedMethodError(Exception):
    """Raised when a registration uses a method outside :data:`SUPPORTED_METHODS`."""


class WebhookRegistry:
    """Thread-safe cache of active webhooks keyed by ``(path, method)``."""

    __slots__ = ("_by_key", "_by_workflow", "_lock")

    def __init__(self) -> None:
        """Create an empty registry."""
        self._by_key: dict[tuple[str, str], WebhookEntry] = {}
        self._by_workflow: dict[str, set[tuple[str, str]]] = {}
        self._lock = threading.RLock()

    def register(self, entry: WebhookEntry) -> None:
        """Insert ``entry`` or raise if its ``(path, method)`` is taken.

        Normalises ``path`` + uppercases ``method`` before writing so callers
        that accidentally pass ``"/foo"`` or ``"get"`` still produce a stable
        key.

        Raises:
            UnsupportedMethodError: when ``method`` is not in
                :data:`SUPPORTED_METHODS`.
            WebhookConflictError: when the key is already registered by a
                different entry.
        """
        normalized = WebhookEntry(
            id=entry.id,
            workflow_id=entry.workflow_id,
            node_id=entry.node_id,
            project_id=entry.project_id,
            path=normalise_path(entry.path),
            method=_normalise_method(entry.method),
            is_dynamic=entry.is_dynamic,
            response_mode=entry.response_mode,
        )
        key = (normalized.path, normalized.method)
        with self._lock:
            existing = self._by_key.get(key)
            if existing is not None and existing.id != normalized.id:
                msg = (
                    f"webhook {normalized.method} /{normalized.path} "
                    f"already registered by {existing.workflow_id}/{existing.node_id}"
                )
                raise WebhookConflictError(msg)
            self._by_key[key] = normalized
            self._by_workflow.setdefault(normalized.workflow_id, set()).add(key)

    def unregister(self, path: str, method: str) -> WebhookEntry | None:
        """Remove the entry at ``(path, method)`` if present and return it."""
        key = (normalise_path(path), _normalise_method(method))
        with self._lock:
            entry = self._by_key.pop(key, None)
            if entry is not None:
                workflow_keys = self._by_workflow.get(entry.workflow_id)
                if workflow_keys is not None:
                    workflow_keys.discard(key)
                    if not workflow_keys:
                        self._by_workflow.pop(entry.workflow_id, None)
            return entry

    def unregister_workflow(self, workflow_id: str) -> list[WebhookEntry]:
        """Drop every entry owned by ``workflow_id`` and return what was removed."""
        with self._lock:
            keys = list(self._by_workflow.pop(workflow_id, set()))
            removed = [self._by_key.pop(key) for key in keys if key in self._by_key]
            return removed

    def match(self, path: str, method: str) -> WebhookEntry | None:
        """Return the entry for ``(path, method)`` or ``None`` if no match."""
        try:
            key = (normalise_path(path), _normalise_method(method))
        except ValueError:
            return None
        with self._lock:
            return self._by_key.get(key)

    def list_for_workflow(self, workflow_id: str) -> list[WebhookEntry]:
        """Return a snapshot of entries owned by ``workflow_id``."""
        with self._lock:
            keys = self._by_workflow.get(workflow_id, set())
            return [self._by_key[k] for k in keys if k in self._by_key]

    def all_entries(self) -> list[WebhookEntry]:
        """Return every entry currently registered (snapshot)."""
        with self._lock:
            return list(self._by_key.values())

    def load(self, entries: Iterable[WebhookEntry]) -> int:
        """Replace the entire cache with ``entries``. Returns the new size."""
        with self._lock:
            self._by_key.clear()
            self._by_workflow.clear()
            count = 0
            for entry in entries:
                self.register(entry)
                count += 1
            return count


def entry_from_entity(entity: WebhookEntity) -> WebhookEntry:
    """Project a :class:`WebhookEntity` row into the in-memory entry shape."""
    return WebhookEntry(
        id=entity.id,
        workflow_id=entity.workflow_id,
        node_id=entity.node_id,
        project_id=entity.project_id,
        path=entity.path,
        method=entity.method,
        is_dynamic=entity.is_dynamic,
        response_mode=entity.response_mode,
    )


def _normalise_method(method: str) -> str:
    upper = method.strip().upper()
    if upper not in SUPPORTED_METHODS:
        msg = f"unsupported HTTP method for webhook: {method!r}"
        raise UnsupportedMethodError(msg)
    return upper
