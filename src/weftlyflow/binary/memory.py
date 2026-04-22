"""In-memory :class:`~weftlyflow.binary.store.BinaryStore` backend.

Primary use is tests and single-process development runs. Not suitable for
production: bytes live on the heap of the current process, vanish on
restart, and are not shared across workers.

Refs produced by this backend carry the scheme ``mem:`` followed by a ULID
key — e.g. ``"mem:01J..."``.
"""

from __future__ import annotations

from typing import ClassVar

from ulid import ULID

from weftlyflow.binary.store import (
    BinaryNotFoundError,
    BinaryStore,
    UnsupportedSchemeError,
)
from weftlyflow.domain.execution import BinaryRef

_SCHEME: str = "mem:"


class InMemoryBinaryStore(BinaryStore):
    """Process-local dictionary-backed binary store."""

    scheme: ClassVar[str] = "mem"

    def __init__(self) -> None:
        """Initialize an empty store."""
        self._blobs: dict[str, bytes] = {}

    async def put(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        mime_type: str = "application/octet-stream",
    ) -> BinaryRef:
        """Store ``data`` under a fresh ULID key and return a ``mem:`` ref."""
        key = str(ULID())
        self._blobs[key] = bytes(data)
        return BinaryRef(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            data_ref=f"{_SCHEME}{key}",
        )

    async def get(self, ref: BinaryRef) -> bytes:
        """Return the bytes for ``ref`` or raise if the key is unknown."""
        key = _key_from_ref(ref)
        try:
            return self._blobs[key]
        except KeyError as exc:
            msg = f"InMemoryBinaryStore: unknown ref {ref.data_ref!r}"
            raise BinaryNotFoundError(msg) from exc

    async def delete(self, ref: BinaryRef) -> None:
        """Drop the blob referenced by ``ref`` — no-op if absent."""
        key = _key_from_ref(ref)
        self._blobs.pop(key, None)


def _key_from_ref(ref: BinaryRef) -> str:
    if not ref.data_ref.startswith(_SCHEME):
        msg = (
            f"InMemoryBinaryStore: ref {ref.data_ref!r} does not start with "
            f"{_SCHEME!r}"
        )
        raise UnsupportedSchemeError(msg)
    return ref.data_ref.removeprefix(_SCHEME)
