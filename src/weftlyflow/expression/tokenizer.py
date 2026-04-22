"""Tokenize a parameter value containing zero or more ``{{ ... }}`` chunks.

The tokenizer is deliberately simple: scan the template left to right,
treat the shortest run starting with ``{{`` and ending with the matching
``}}`` as an expression chunk, and leave the rest as literal text. A
stray ``{{`` without a closing ``}}`` is a syntax error.

We do **not** try to support nested curly braces — Weftlyflow expressions are
one-liners, not templates.
"""

from __future__ import annotations

from dataclasses import dataclass

from weftlyflow.expression.errors import ExpressionSyntaxError

OPEN_TAG: str = "{{"
CLOSE_TAG: str = "}}"


@dataclass(slots=True, frozen=True)
class LiteralChunk:
    """Plain text copied through unchanged."""

    text: str


@dataclass(slots=True, frozen=True)
class ExpressionChunk:
    """A Python expression extracted from between ``{{`` and ``}}``.

    Attributes:
        source: The raw source (no braces, ``.strip()``ed).
        offset: Byte offset of the opening ``{{`` in the original template
            — surfaced in error messages.
    """

    source: str
    offset: int


Chunk = LiteralChunk | ExpressionChunk


def tokenize(template: str) -> list[Chunk]:
    """Return the left-to-right ordered list of chunks for ``template``.

    ``tokenize("")`` returns an empty list — callers should guard against
    the empty result when they want to emit the empty string verbatim.
    """
    chunks: list[Chunk] = []
    cursor = 0
    length = len(template)
    while cursor < length:
        open_at = template.find(OPEN_TAG, cursor)
        if open_at == -1:
            chunks.append(LiteralChunk(template[cursor:]))
            break
        if open_at > cursor:
            chunks.append(LiteralChunk(template[cursor:open_at]))
        close_at = template.find(CLOSE_TAG, open_at + len(OPEN_TAG))
        if close_at == -1:
            msg = (
                "unterminated expression: missing '}}' after "
                f"column {open_at + 1} in {template!r}"
            )
            raise ExpressionSyntaxError(msg)
        source = template[open_at + len(OPEN_TAG) : close_at].strip()
        if not source:
            msg = f"empty expression at column {open_at + 1} in {template!r}"
            raise ExpressionSyntaxError(msg)
        chunks.append(ExpressionChunk(source=source, offset=open_at))
        cursor = close_at + len(CLOSE_TAG)
    return chunks


def is_single_expression(chunks: list[Chunk]) -> bool:
    """Return True iff ``chunks`` is exactly one :class:`ExpressionChunk`.

    Useful for the resolver: a template that is exactly one ``{{ ... }}`` chunk
    should return the raw evaluated value (preserving type), whereas
    mixed templates always stringify.
    """
    return len(chunks) == 1 and isinstance(chunks[0], ExpressionChunk)


def contains_expression(template: str) -> bool:
    """Cheap check — does the template contain **any** ``{{``?

    Used by the resolver to short-circuit before tokenising when the
    parameter is obviously literal.
    """
    return OPEN_TAG in template
