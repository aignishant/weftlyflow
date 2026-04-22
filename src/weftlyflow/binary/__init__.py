"""Binary payload storage — pluggable backends for BinaryRef data.

The :class:`BinaryStore` Protocol is the single interface nodes use to
read or write the bytes behind a :class:`~weftlyflow.domain.execution.BinaryRef`.
Backends implement the Protocol; the engine wires one concrete instance
onto :class:`~weftlyflow.engine.context.ExecutionContext` so nodes never
know whether the bytes live on disk, in memory, in Postgres, or in S3.
"""

from __future__ import annotations

from weftlyflow.binary.filesystem import FilesystemBinaryStore
from weftlyflow.binary.memory import InMemoryBinaryStore
from weftlyflow.binary.store import BinaryStore, BinaryStoreError

__all__ = [
    "BinaryStore",
    "BinaryStoreError",
    "FilesystemBinaryStore",
    "InMemoryBinaryStore",
]
