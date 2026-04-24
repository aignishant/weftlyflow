"""Embed Local node - deterministic hashing embeddings, no API required.

Wraps :func:`weftlyflow.nodes.ai.embed_local.hasher.embed` so the
``text_splitter -> embed -> vector_memory`` chain can be exercised
end-to-end without an OpenAI key. Useful in:

* CI smoke tests for RAG workflows.
* Local development where API calls would be wasteful.
* Hermetic demos.

Parameters:

* ``text_field`` - JSON key holding the text (default ``"chunk"`` so
  it drops in after ``text_splitter``'s per-chunk fan-out mode).
* ``output_field`` - where to write the vector (default
  ``"embedding"`` - matches common RAG conventions).
* ``dimensions`` - vector length (default ``256``).
* ``normalize`` - L2-normalise to a unit vector so cosine and dot
  metrics agree (default ``True``).

Output: the input item with ``output_field`` populated, plus the
convenience fields ``embedding_dimensions`` and
``embedding_model`` = ``"weftlyflow.embed_local"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertySchema,
)
from weftlyflow.nodes.ai.embed_local.hasher import embed
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_DEFAULT_TEXT_FIELD: str = "chunk"
_DEFAULT_OUTPUT_FIELD: str = "embedding"
_DEFAULT_DIMENSIONS: int = 256
_MODEL_TAG: str = "weftlyflow.embed_local"


class EmbedLocalNode(BaseNode):
    """Produce deterministic hashing embeddings, one vector per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.embed_local",
        version=1,
        display_name="Embed (Local)",
        description=(
            "Deterministic feature-hashing embeddings. No network, no "
            "API key - pair with vector_memory for hermetic RAG tests."
        ),
        icon="icons/embed-local.svg",
        category=NodeCategory.AI,
        group=["ai", "retrieval"],
        properties=[
            PropertySchema(
                name="text_field",
                display_name="Text Field",
                type="string",
                default=_DEFAULT_TEXT_FIELD,
                description="JSON key whose value is embedded.",
            ),
            PropertySchema(
                name="output_field",
                display_name="Output Field",
                type="string",
                default=_DEFAULT_OUTPUT_FIELD,
                description="JSON key the embedding is written to.",
            ),
            PropertySchema(
                name="dimensions",
                display_name="Dimensions",
                type="number",
                default=_DEFAULT_DIMENSIONS,
                description="Vector length.",
            ),
            PropertySchema(
                name="normalize",
                display_name="Normalize",
                type="boolean",
                default=True,
                description="L2-normalise so cosine and dot metrics agree.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Emit one embedded item per input item."""
        return [[_embed_one(ctx, item) for item in items]]


def _embed_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    text_field = str(params.get("text_field") or _DEFAULT_TEXT_FIELD)
    output_field = str(params.get("output_field") or _DEFAULT_OUTPUT_FIELD)
    dimensions = _coerce_dimensions(params.get("dimensions"), ctx)
    normalize = _coerce_bool(params.get("normalize"), default=True)

    source = item.json if isinstance(item.json, dict) else {}
    raw = source.get(text_field, "")
    text = raw if isinstance(raw, str) else str(raw)

    try:
        vector = embed(text, dimensions=dimensions, normalize=normalize)
    except ValueError as exc:
        raise NodeExecutionError(
            f"Embed Local: {exc}", node_id=ctx.node.id, original=exc,
        ) from exc

    return Item(
        json={
            **source,
            output_field: vector,
            "embedding_dimensions": dimensions,
            "embedding_model": _MODEL_TAG,
        },
        binary=item.binary,
        paired_item=item.paired_item,
        error=item.error,
    )


def _coerce_dimensions(raw: Any, ctx: ExecutionContext) -> int:
    if raw is None or raw == "":
        return _DEFAULT_DIMENSIONS
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise NodeExecutionError(
            "Embed Local: 'dimensions' must be an integer",
            node_id=ctx.node.id,
            original=exc,
        ) from exc
    if value <= 0:
        msg = "Embed Local: 'dimensions' must be > 0"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return value


def _coerce_bool(raw: Any, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes", "on"}
    return bool(raw)
