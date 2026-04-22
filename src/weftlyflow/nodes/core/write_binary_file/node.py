"""Write Binary File node — copy an item's binary ref to an output path.

For each input item the node reads the :class:`BinaryRef` at
``binary_property`` and copies its bytes to the configured ``path``.

Filesystem-scheme refs (``fs:<abs path>``) are resolved via ``shutil`` for
a zero-copy fast path. Refs with any other scheme are delegated to the
execution's configured
:class:`~weftlyflow.binary.store.BinaryStore` — if no store is wired,
non-fs schemes raise :class:`ValueError`.

The item is emitted unchanged on the ``main`` output port so downstream
nodes can reference the original JSON payload.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import ClassVar

from weftlyflow.binary.store import BinaryStore
from weftlyflow.domain.execution import BinaryRef, Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode

_DEFAULT_BINARY_PROPERTY: str = "data"
_FS_SCHEME: str = "fs:"


class WriteBinaryFileNode(BaseNode):
    """Write each item's binary payload to the configured filesystem path."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.write_binary_file",
        version=1,
        display_name="Write Binary File",
        description="Copy item.binary bytes to a target path on disk.",
        icon="icons/write-binary-file.svg",
        category=NodeCategory.CORE,
        group=["files"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="path",
                display_name="Destination path",
                type="string",
                default="",
                required=True,
                description="Absolute output path. Supports {{ expressions }}.",
            ),
            PropertySchema(
                name="binary_property",
                display_name="Binary property name",
                type="string",
                default=_DEFAULT_BINARY_PROPERTY,
                description="Key under item.binary to read the source bytes from.",
            ),
            PropertySchema(
                name="overwrite",
                display_name="Overwrite",
                type="boolean",
                default=True,
                description="Overwrite the destination if it already exists.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Persist each item's binary ref to disk and pass the item through."""
        binary_property = str(
            ctx.param("binary_property", _DEFAULT_BINARY_PROPERTY),
        ).strip() or _DEFAULT_BINARY_PROPERTY
        overwrite = bool(ctx.param("overwrite", True))
        for item in items:
            resolved_path = str(ctx.resolved_param("path", item=item) or "").strip()
            if not resolved_path:
                msg = "Write Binary File: 'path' is required"
                raise ValueError(msg)
            ref = item.binary.get(binary_property)
            if not isinstance(ref, BinaryRef):
                msg = (
                    f"Write Binary File: item.binary[{binary_property!r}] "
                    "is missing or not a BinaryRef"
                )
                raise ValueError(msg)
            await _write_ref(
                ref,
                destination=resolved_path,
                overwrite=overwrite,
                store=ctx.binary_store,
            )
        return [list(items)]


async def _write_ref(
    ref: BinaryRef,
    *,
    destination: str,
    overwrite: bool,
    store: BinaryStore | None,
) -> None:
    dest = Path(destination).expanduser()
    if dest.exists() and not overwrite:
        msg = f"Write Binary File: destination {dest!s} exists and overwrite=False"
        raise ValueError(msg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if ref.data_ref.startswith(_FS_SCHEME):
        source = Path(ref.data_ref.removeprefix(_FS_SCHEME)).expanduser()
        if not source.is_file():
            msg = f"Write Binary File: source {source!s} does not exist"
            raise ValueError(msg)
        shutil.copyfile(source, dest)
        return
    if store is None:
        msg = (
            f"Write Binary File: unsupported data_ref scheme "
            f"{ref.data_ref!r} — only 'fs:' is implemented"
        )
        raise ValueError(msg)
    data = await store.get(ref)
    dest.write_bytes(data)
