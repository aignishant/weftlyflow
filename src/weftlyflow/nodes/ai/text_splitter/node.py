"""Text Splitter node - chunk long text for embedding / RAG pipelines.

Splits the value at ``text_field`` into overlapping chunks and either
fans out one output item per chunk (the default) or returns a single
item with a ``chunks`` list. The fan-out mode is what pairs cleanly
with the OpenAI embedding operation downstream: one row in, N rows
out, each carrying a ``chunk``, ``chunk_index``, and ``chunk_total``.

Parameters:

* ``text_field`` - JSON key holding the text (default ``"text"``).
* ``chunk_size`` - max characters per chunk (default ``1000``).
* ``chunk_overlap`` - characters shared between neighbouring chunks
  (default ``100``).
* ``separators`` - optional JSON list of separator strings in
  priority order. When omitted, a sensible default handles prose.
* ``output_mode`` - ``per_chunk`` (default, fan out) or ``list``
  (one output item with a ``chunks`` field).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.ai.text_splitter.splitter import split_text
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_MODE_PER_CHUNK: str = "per_chunk"
_MODE_LIST: str = "list"
_DEFAULT_TEXT_FIELD: str = "text"
_DEFAULT_CHUNK_SIZE: int = 1000
_DEFAULT_CHUNK_OVERLAP: int = 100


class TextSplitterNode(BaseNode):
    """Chunk text from each input item for downstream embedding."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.text_splitter",
        version=1,
        display_name="Text Splitter",
        description=(
            "Split long text into overlapping chunks. Pairs with "
            "embedding nodes for RAG pipelines."
        ),
        icon="icons/text-splitter.svg",
        category=NodeCategory.AI,
        group=["ai", "retrieval"],
        properties=[
            PropertySchema(
                name="text_field",
                display_name="Text Field",
                type="string",
                default=_DEFAULT_TEXT_FIELD,
                description="JSON key whose value is the text to split.",
            ),
            PropertySchema(
                name="chunk_size",
                display_name="Chunk Size",
                type="number",
                default=_DEFAULT_CHUNK_SIZE,
                description="Maximum characters per chunk.",
            ),
            PropertySchema(
                name="chunk_overlap",
                display_name="Chunk Overlap",
                type="number",
                default=_DEFAULT_CHUNK_OVERLAP,
                description="Characters shared between adjacent chunks.",
            ),
            PropertySchema(
                name="separators",
                display_name="Separators",
                type="json",
                description=(
                    "Optional JSON list of priority-ordered separator "
                    "strings. Leave empty for the default."
                ),
            ),
            PropertySchema(
                name="output_mode",
                display_name="Output Mode",
                type="options",
                default=_MODE_PER_CHUNK,
                options=[
                    PropertyOption(
                        value=_MODE_PER_CHUNK,
                        label="One item per chunk",
                    ),
                    PropertyOption(
                        value=_MODE_LIST,
                        label="Single item with chunks list",
                    ),
                ],
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Return chunked outputs for every input item."""
        out: list[Item] = []
        for item in items:
            out.extend(_split_one(ctx, item))
        return [out]


def _split_one(ctx: ExecutionContext, item: Item) -> list[Item]:
    params = ctx.resolved_params(item=item)
    text_field = str(params.get("text_field") or _DEFAULT_TEXT_FIELD)
    chunk_size = _coerce_int(
        params.get("chunk_size"), _DEFAULT_CHUNK_SIZE, "chunk_size", ctx,
    )
    chunk_overlap = _coerce_int(
        params.get("chunk_overlap"),
        _DEFAULT_CHUNK_OVERLAP,
        "chunk_overlap",
        ctx,
    )
    separators = _coerce_separators(params.get("separators"), ctx)
    mode = str(params.get("output_mode") or _MODE_PER_CHUNK)

    source = item.json if isinstance(item.json, dict) else {}
    raw = source.get(text_field, "")
    text = raw if isinstance(raw, str) else str(raw)

    try:
        chunks = split_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
        )
    except ValueError as exc:
        raise NodeExecutionError(
            f"Text Splitter: {exc}", node_id=ctx.node.id, original=exc,
        ) from exc

    if mode == _MODE_LIST:
        payload: dict[str, Any] = dict(source)
        payload["chunks"] = chunks
        payload["chunk_total"] = len(chunks)
        return [
            Item(
                json=payload,
                binary=item.binary,
                paired_item=item.paired_item,
                error=item.error,
            ),
        ]

    if mode != _MODE_PER_CHUNK:
        raise NodeExecutionError(
            f"Text Splitter: unknown output_mode {mode!r}", node_id=ctx.node.id,
        )
    total = len(chunks)
    return [
        Item(
            json={
                **source,
                "chunk": chunk,
                "chunk_index": idx,
                "chunk_total": total,
            },
            binary=item.binary,
            paired_item=item.paired_item,
            error=item.error,
        )
        for idx, chunk in enumerate(chunks)
    ]


def _coerce_int(
    raw: Any,
    default: int,
    name: str,
    ctx: ExecutionContext,
) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise NodeExecutionError(
            f"Text Splitter: {name} must be an integer",
            node_id=ctx.node.id,
            original=exc,
        ) from exc


def _coerce_separators(
    raw: Any,
    ctx: ExecutionContext,
) -> list[str] | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, list):
        raise NodeExecutionError(
            "Text Splitter: 'separators' must be a JSON array of strings",
            node_id=ctx.node.id,
        )
    coerced: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise NodeExecutionError(
                "Text Splitter: every separator must be a string",
                node_id=ctx.node.id,
            )
        coerced.append(entry)
    return coerced or None
