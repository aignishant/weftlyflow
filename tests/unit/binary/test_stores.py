"""Round-trip tests for the in-memory and filesystem binary stores.

Each store is exercised via the :class:`~weftlyflow.binary.store.BinaryStore`
Protocol surface — put/get/delete plus the negative cases (unknown ref,
foreign scheme, path escape).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weftlyflow.binary import FilesystemBinaryStore, InMemoryBinaryStore
from weftlyflow.binary.store import (
    BinaryNotFoundError,
    BinaryStoreError,
    UnsupportedSchemeError,
)
from weftlyflow.domain.execution import BinaryRef

pytestmark = pytest.mark.asyncio


# --- InMemoryBinaryStore ----------------------------------------------------


async def test_memory_store_round_trip() -> None:
    store = InMemoryBinaryStore()
    ref = await store.put(b"hello", filename="g.txt", mime_type="text/plain")
    assert ref.data_ref.startswith("mem:")
    assert ref.size_bytes == 5
    assert ref.filename == "g.txt"
    assert ref.mime_type == "text/plain"
    assert await store.get(ref) == b"hello"


async def test_memory_store_get_unknown_ref_raises() -> None:
    store = InMemoryBinaryStore()
    ghost = BinaryRef(filename=None, mime_type="x", size_bytes=0, data_ref="mem:nope")
    with pytest.raises(BinaryNotFoundError):
        await store.get(ghost)


async def test_memory_store_rejects_foreign_scheme() -> None:
    store = InMemoryBinaryStore()
    alien = BinaryRef(filename=None, mime_type="x", size_bytes=0, data_ref="fs:/tmp/x")
    with pytest.raises(UnsupportedSchemeError):
        await store.get(alien)


async def test_memory_store_delete_is_idempotent() -> None:
    store = InMemoryBinaryStore()
    ref = await store.put(b"a")
    await store.delete(ref)
    await store.delete(ref)  # second call is a no-op
    with pytest.raises(BinaryNotFoundError):
        await store.get(ref)


# --- FilesystemBinaryStore --------------------------------------------------


async def test_fs_store_round_trip(tmp_path: Path) -> None:
    store = FilesystemBinaryStore(tmp_path / "blobs")
    ref = await store.put(b"payload", filename="p.bin", mime_type="application/x-bin")
    assert ref.data_ref.startswith(f"fs:{store.root}")
    assert ref.size_bytes == 7
    blob_path = Path(ref.data_ref.removeprefix("fs:"))
    assert blob_path.parent == store.root
    assert blob_path.read_bytes() == b"payload"
    assert await store.get(ref) == b"payload"


async def test_fs_store_creates_root_if_missing(tmp_path: Path) -> None:
    root = tmp_path / "does" / "not" / "exist"
    store = FilesystemBinaryStore(root)
    assert store.root.is_dir()


async def test_fs_store_get_missing_blob_raises(tmp_path: Path) -> None:
    store = FilesystemBinaryStore(tmp_path)
    missing = BinaryRef(
        filename=None, mime_type="x", size_bytes=0,
        data_ref=f"fs:{tmp_path / 'absent.bin'}",
    )
    with pytest.raises(BinaryNotFoundError):
        await store.get(missing)


async def test_fs_store_rejects_path_outside_root(tmp_path: Path) -> None:
    store = FilesystemBinaryStore(tmp_path / "blobs")
    outside = tmp_path / "elsewhere.bin"
    outside.write_bytes(b"x")
    escape = BinaryRef(
        filename=None, mime_type="x", size_bytes=1, data_ref=f"fs:{outside}",
    )
    with pytest.raises(BinaryStoreError, match="outside root"):
        await store.get(escape)


async def test_fs_store_rejects_foreign_scheme(tmp_path: Path) -> None:
    store = FilesystemBinaryStore(tmp_path)
    alien = BinaryRef(filename=None, mime_type="x", size_bytes=0, data_ref="mem:abc")
    with pytest.raises(UnsupportedSchemeError):
        await store.get(alien)


async def test_fs_store_delete_is_idempotent(tmp_path: Path) -> None:
    store = FilesystemBinaryStore(tmp_path)
    ref = await store.put(b"a")
    await store.delete(ref)
    await store.delete(ref)
    with pytest.raises(BinaryNotFoundError):
        await store.get(ref)
