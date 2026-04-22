"""Read Binary File node — attach a file's metadata as a binary ref.

For each input item, the node reads the configured ``path`` from the local
filesystem, computes the size + MIME type, and attaches a
:class:`~weftlyflow.domain.execution.BinaryRef` to
``item.binary[<binary_property>]`` with ``data_ref="fs:<abs path>"``.

The ``path`` parameter is resolved through the expression engine on every
item, so ``{{ $json.filename }}`` works as expected. To avoid holding file
bytes in memory, the node stores a pointer rather than the raw content —
downstream "Write Binary File" or HTTP Request (upload) nodes resolve the
pointer when they actually need the bytes.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import ClassVar

from weftlyflow.domain.execution import BinaryRef, Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode

_DEFAULT_BINARY_PROPERTY: str = "data"
_DEFAULT_MIME: str = "application/octet-stream"
_FS_SCHEME: str = "fs:"


class ReadBinaryFileNode(BaseNode):
    """Attach a filesystem binary ref to every input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.read_binary_file",
        version=1,
        display_name="Read Binary File",
        description="Load a file from disk and attach it to the item's binary map.",
        icon="icons/read-binary-file.svg",
        category=NodeCategory.CORE,
        group=["files"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="path",
                display_name="File path",
                type="string",
                default="",
                required=True,
                description="Absolute path to the file. Supports {{ expressions }}.",
            ),
            PropertySchema(
                name="binary_property",
                display_name="Binary property name",
                type="string",
                default=_DEFAULT_BINARY_PROPERTY,
                description="Key under item.binary to attach the reference.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Read each item's configured file and attach a BinaryRef."""
        binary_property = str(
            ctx.param("binary_property", _DEFAULT_BINARY_PROPERTY),
        ).strip() or _DEFAULT_BINARY_PROPERTY
        out: list[Item] = []
        for item in items:
            resolved_path = str(ctx.resolved_param("path", item=item) or "").strip()
            if not resolved_path:
                msg = "Read Binary File: 'path' is required"
                raise ValueError(msg)
            out.append(
                _attach_binary(item, path=resolved_path, binary_property=binary_property),
            )
        return [out]


def _attach_binary(item: Item, *, path: str, binary_property: str) -> Item:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        msg = f"Read Binary File: {path!r} is not a file"
        raise ValueError(msg)
    mime_type, _ = mimetypes.guess_type(file_path.name)
    ref = BinaryRef(
        filename=file_path.name,
        mime_type=mime_type or _DEFAULT_MIME,
        size_bytes=file_path.stat().st_size,
        data_ref=f"{_FS_SCHEME}{file_path}",
    )
    merged_binary = dict(item.binary)
    merged_binary[binary_property] = ref
    return Item(
        json=dict(item.json),
        binary=merged_binary,
        paired_item=list(item.paired_item),
        error=item.error,
    )
