"""Pluggable storage backends for execution payloads.

The metadata row (``executions``) is always in Postgres — it's small, it's
indexed, and the server lists it constantly. The bulky twin (``workflow_snapshot``
plus per-node ``run_data``) is what this module abstracts.

Why pluggable:

* **DB bloat** — a busy workflow with image-heavy payloads can push row sizes
  into the megabyte range; keeping them in Postgres balloons backup size and
  slows vacuum.
* **Retention ergonomics** — filesystem / object-store backends let operators
  bucket old payloads onto cheap storage or expire them via lifecycle rules
  without touching the primary DB.

Backend contract:

* :meth:`ExecutionDataStore.write` takes a :class:`StoredExecutionPayload` and
  returns a :class:`StoredDataRow` — the exact shape the repository writes to
  :class:`~weftlyflow.db.entities.execution_data.ExecutionDataEntity`. The DB
  backend inlines the payload into the JSON columns; external backends clear
  the JSON columns and populate ``external_ref``.
* :meth:`ExecutionDataStore.read` reverses the operation given the entity's
  stored row.
* :meth:`ExecutionDataStore.delete` is best-effort — missing external blobs
  must not raise.

The default store is chosen from ``WEFTLYFLOW_EXECUTION_DATA_BACKEND``; see
:func:`get_default_store`.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import structlog

log = structlog.get_logger(__name__)

STORAGE_KIND_DB = "db"
STORAGE_KIND_FS = "fs"


@dataclass(slots=True, frozen=True)
class StoredExecutionPayload:
    """The two JSON blobs that belong to one execution, in pure-data form."""

    workflow_snapshot: dict[str, Any]
    run_data: dict[str, Any]


@dataclass(slots=True, frozen=True)
class StoredDataRow:
    """The shape of an ``execution_data`` row the repository will persist.

    Attributes:
        storage_kind: Which backend owns the payload — ``"db"`` means the
            payload is inlined in this row; anything else means ``external_ref``
            points to it.
        external_ref: Opaque handle understood by the producing store.
            ``None`` for DB storage.
        workflow_snapshot: JSON-safe snapshot dict. Empty ``{}`` when external.
        run_data: JSON-safe run-data dict. Empty ``{}`` when external.
    """

    storage_kind: str
    external_ref: str | None
    workflow_snapshot: dict[str, Any]
    run_data: dict[str, Any]


@runtime_checkable
class ExecutionDataStore(Protocol):
    """Contract for execution-payload backends.

    Implementations must be concurrency-safe for concurrent ``write`` /
    ``read`` calls against different ``execution_id`` values; the repository
    never calls the store with the same id in parallel for a single
    execution.
    """

    kind: str

    async def write(
        self, execution_id: str, payload: StoredExecutionPayload,
    ) -> StoredDataRow:
        """Persist ``payload`` and return the row the repository should save."""
        ...

    async def read(
        self, execution_id: str, row: StoredDataRow,
    ) -> StoredExecutionPayload:
        """Return the payload referenced by ``row``."""
        ...

    async def delete(self, execution_id: str, row: StoredDataRow) -> None:
        """Best-effort removal of any external blobs backing ``row``."""
        ...


class DbExecutionDataStore:
    """Default store — the payload lives inline in the DB row.

    Example:
        >>> store = DbExecutionDataStore()
        >>> row = await store.write("exec_1", StoredExecutionPayload({}, {}))  # doctest: +SKIP
        >>> row.storage_kind
        'db'
    """

    kind: str = STORAGE_KIND_DB

    async def write(
        self, execution_id: str, payload: StoredExecutionPayload,
    ) -> StoredDataRow:
        """Return a row with the payload inlined — no external IO."""
        del execution_id
        return StoredDataRow(
            storage_kind=self.kind,
            external_ref=None,
            workflow_snapshot=payload.workflow_snapshot,
            run_data=payload.run_data,
        )

    async def read(
        self, execution_id: str, row: StoredDataRow,
    ) -> StoredExecutionPayload:
        """Return the inlined payload. Raises ``ValueError`` on kind mismatch."""
        del execution_id
        if row.storage_kind != self.kind:
            msg = f"DbExecutionDataStore cannot read storage_kind={row.storage_kind!r}"
            raise ValueError(msg)
        return StoredExecutionPayload(
            workflow_snapshot=row.workflow_snapshot,
            run_data=row.run_data,
        )

    async def delete(self, execution_id: str, row: StoredDataRow) -> None:
        """No-op — the DB row is removed by ``ON DELETE CASCADE``."""
        del execution_id, row


class FilesystemExecutionDataStore:
    """Write payloads as single JSON files under ``base_path``.

    Layout: ``<base_path>/<yyyy>/<mm>/<execution_id>.json``. The YYYY/MM shards
    prevent any single directory from accumulating millions of entries; the
    execution id (ULIDs) is already globally unique so no further sharding is
    needed.

    Writes are atomic on POSIX: the JSON is written to a sibling tempfile then
    ``os.replace``'d into place.

    Example:
        >>> store = FilesystemExecutionDataStore(base_path="/var/lib/weftlyflow/exec")
        >>> row = await store.write("exec_1", StoredExecutionPayload({}, {}))  # doctest: +SKIP
        >>> row.storage_kind, row.external_ref  # doctest: +SKIP
        ('fs', '2026/04/exec_1.json')
    """

    kind: str = STORAGE_KIND_FS

    __slots__ = ("_base_path",)

    def __init__(self, *, base_path: str | Path) -> None:
        """Bind to ``base_path``. The directory is created on first write."""
        self._base_path = Path(base_path)

    async def write(
        self, execution_id: str, payload: StoredExecutionPayload,
    ) -> StoredDataRow:
        """Serialise ``payload`` to ``<base>/YYYY/MM/<id>.json`` atomically."""
        relpath = self._relpath_for(execution_id)
        abspath = self._base_path / relpath
        abspath.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            {
                "workflow_snapshot": payload.workflow_snapshot,
                "run_data": payload.run_data,
            },
        )
        fd, tmp = tempfile.mkstemp(
            prefix=f".{execution_id}.", suffix=".json", dir=abspath.parent,
        )
        tmp_path = Path(tmp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(body)
            tmp_path.replace(abspath)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                tmp_path.unlink()
            raise
        return StoredDataRow(
            storage_kind=self.kind,
            external_ref=str(relpath),
            workflow_snapshot={},
            run_data={},
        )

    async def read(
        self, execution_id: str, row: StoredDataRow,
    ) -> StoredExecutionPayload:
        """Load and return the payload referenced by ``row.external_ref``."""
        if row.storage_kind != self.kind:
            msg = f"FilesystemExecutionDataStore cannot read storage_kind={row.storage_kind!r}"
            raise ValueError(msg)
        if row.external_ref is None:
            msg = f"execution {execution_id!r} has fs storage but no external_ref"
            raise ValueError(msg)
        abspath = self._base_path / row.external_ref
        raw = abspath.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            msg = f"execution-data file {abspath} is not a JSON object"
            raise ValueError(msg)
        return StoredExecutionPayload(
            workflow_snapshot=dict(data.get("workflow_snapshot", {})),
            run_data=dict(data.get("run_data", {})),
        )

    async def delete(self, execution_id: str, row: StoredDataRow) -> None:
        """Remove the backing file if present; swallow missing-file errors."""
        del execution_id
        if row.storage_kind != self.kind or row.external_ref is None:
            return
        abspath = self._base_path / row.external_ref
        try:
            abspath.unlink()
        except FileNotFoundError:
            log.debug(
                "execution-data file already gone",
                path=str(abspath),
            )

    @staticmethod
    def _relpath_for(execution_id: str) -> Path:
        # ULID-based ids start with a time component; shard on the current
        # filesystem clock rather than parsing the id so tests can use fake
        # ids freely. The subdir is stable enough for the intended purpose
        # (avoiding one fat directory) without inventing extra parsing.
        now = datetime.now(UTC)
        return Path(f"{now.year:04d}") / f"{now.month:02d}" / f"{execution_id}.json"


# Module-level cache wrapped in a single-item list so `global` mutation
# isn't needed — ruff's PLW0603 flags module-global writes as fragile.
_DEFAULT_STORE: list[ExecutionDataStore | None] = [None]


def _build_default_store() -> ExecutionDataStore:
    from weftlyflow.config import get_settings  # noqa: PLC0415 — avoid import cycle at module load

    settings = get_settings()
    backend = settings.execution_data_backend.lower()
    if backend == STORAGE_KIND_FS:
        if not settings.execution_data_fs_path:
            msg = "execution_data_backend='fs' but execution_data_fs_path is empty"
            raise ValueError(msg)
        return FilesystemExecutionDataStore(
            base_path=settings.execution_data_fs_path,
        )
    if backend == STORAGE_KIND_DB:
        return DbExecutionDataStore()
    msg = f"unknown execution_data_backend {backend!r}"
    raise ValueError(msg)


def get_default_store() -> ExecutionDataStore:
    """Return the process-wide default store, building it from settings once.

    The store is cached. Tests that want to swap the store can call
    :func:`set_default_store` or construct a store directly and pass it to
    :class:`~weftlyflow.db.repositories.execution_repo.ExecutionRepository`.
    """
    cached = _DEFAULT_STORE[0]
    if cached is None:
        cached = _build_default_store()
        _DEFAULT_STORE[0] = cached
    return cached


def set_default_store(store: ExecutionDataStore | None) -> None:
    """Override (or reset) the process-wide default store. Test-only seam."""
    _DEFAULT_STORE[0] = store


__all__ = [
    "STORAGE_KIND_DB",
    "STORAGE_KIND_FS",
    "DbExecutionDataStore",
    "ExecutionDataStore",
    "FilesystemExecutionDataStore",
    "StoredDataRow",
    "StoredExecutionPayload",
    "get_default_store",
    "set_default_store",
]
