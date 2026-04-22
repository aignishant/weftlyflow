"""Filesystem :class:`~weftlyflow.binary.store.BinaryStore` backend.

Writes blobs as files under a configured root directory — typically
``$WEFTLYFLOW_BINARY_ROOT`` (defaulting to ``/var/lib/weftlyflow/blobs`` in
self-hosted deploys). Reads are scoped to that same root: ``get`` rejects
refs whose resolved path escapes the root, defending against
directory-traversal attacks that could be mounted by crafted ``BinaryRef``
values flowing through the expression engine.

Refs produced by this backend carry the scheme ``fs:`` followed by the
absolute path of the blob file — e.g. ``"fs:/var/lib/weftlyflow/blobs/01J...bin"``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import ClassVar

from ulid import ULID

from weftlyflow.binary.store import (
    BinaryNotFoundError,
    BinaryStore,
    BinaryStoreError,
    UnsupportedSchemeError,
)
from weftlyflow.domain.execution import BinaryRef

_SCHEME: str = "fs:"
_BLOB_SUFFIX: str = ".bin"


class FilesystemBinaryStore(BinaryStore):
    """Store blobs as files under a single root directory."""

    scheme: ClassVar[str] = "fs"

    def __init__(self, root: Path | str) -> None:
        """Initialize the store rooted at ``root`` (created if absent)."""
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        """Return the resolved root directory under which blobs are persisted."""
        return self._root

    async def put(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        mime_type: str = "application/octet-stream",
    ) -> BinaryRef:
        """Write ``data`` to a new file under the root and return its ``fs:`` ref."""
        key = str(ULID())
        blob_path = self._root / f"{key}{_BLOB_SUFFIX}"
        await asyncio.to_thread(blob_path.write_bytes, bytes(data))
        return BinaryRef(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            data_ref=f"{_SCHEME}{blob_path}",
        )

    async def get(self, ref: BinaryRef) -> bytes:
        """Return the bytes of the file ``ref`` points at, if under root."""
        path = self._path_from_ref(ref)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            msg = f"FilesystemBinaryStore: blob not found at {path!s}"
            raise BinaryNotFoundError(msg) from exc

    async def delete(self, ref: BinaryRef) -> None:
        """Remove the file backing ``ref`` — no-op if already gone."""
        path = self._path_from_ref(ref)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            return

    def _path_from_ref(self, ref: BinaryRef) -> Path:
        if not ref.data_ref.startswith(_SCHEME):
            msg = (
                f"FilesystemBinaryStore: ref {ref.data_ref!r} does not start "
                f"with {_SCHEME!r}"
            )
            raise UnsupportedSchemeError(msg)
        raw = ref.data_ref.removeprefix(_SCHEME)
        candidate = Path(raw).expanduser().resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            msg = (
                f"FilesystemBinaryStore: refusing to access {candidate!s} — "
                f"outside root {self._root!s}"
            )
            raise BinaryStoreError(msg) from exc
        return candidate
