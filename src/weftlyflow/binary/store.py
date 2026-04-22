"""Binary store protocol — the interface nodes use to read/write blob bytes.

Nodes that produce or consume binary data (HTTP Request with a file upload,
Read/Write Binary File, AI image nodes, etc.) never hold raw bytes in the
item JSON. They carry a :class:`~weftlyflow.domain.execution.BinaryRef` and
call into a :class:`BinaryStore` to resolve the underlying bytes.

The engine wires a concrete store onto
:class:`~weftlyflow.engine.context.ExecutionContext.binary_store`. Backends
are addressed by the ``scheme`` prefix of ``BinaryRef.data_ref`` — e.g.
``"mem:01J..."`` for :class:`~weftlyflow.binary.memory.InMemoryBinaryStore`,
``"fs:/var/lib/weftlyflow/blobs/01J..."`` for
:class:`~weftlyflow.binary.filesystem.FilesystemBinaryStore`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weftlyflow.domain.errors import WeftlyflowError

if TYPE_CHECKING:
    from weftlyflow.domain.execution import BinaryRef


class BinaryStoreError(WeftlyflowError):
    """Any failure raised by a :class:`BinaryStore` implementation."""


class BinaryNotFoundError(BinaryStoreError):
    """The ``data_ref`` does not point at a known blob in this store."""


class UnsupportedSchemeError(BinaryStoreError):
    """The store was asked to operate on a ref whose scheme it does not own."""


@runtime_checkable
class BinaryStore(Protocol):
    """Pluggable backend for reading and writing the bytes behind a ``BinaryRef``.

    Implementations must be safe to call from multiple asyncio tasks
    concurrently. They must raise :class:`BinaryNotFoundError` for unknown
    refs and :class:`UnsupportedSchemeError` for refs whose scheme they do
    not own.
    """

    scheme: ClassVar[str]

    async def put(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        mime_type: str = "application/octet-stream",
    ) -> BinaryRef:
        """Persist ``data`` and return a :class:`BinaryRef` that resolves to it."""

    async def get(self, ref: BinaryRef) -> bytes:
        """Return the bytes referenced by ``ref``.

        Raises:
            BinaryNotFoundError: ``ref.data_ref`` is unknown to this store.
            UnsupportedSchemeError: ``ref.data_ref`` belongs to a different backend.
        """

    async def delete(self, ref: BinaryRef) -> None:
        """Remove the blob referenced by ``ref``.

        Idempotent — deleting an unknown ref is a no-op.
        """
