r"""Recursive text splitter used by the ``text_splitter`` node.

The algorithm is the same greedy recursive-descent approach popularised
by LangChain's ``RecursiveCharacterTextSplitter``, reimplemented from
scratch with no external dependency and no identifiers copied. The
splitter walks a *separator priority list* - ``["\\n\\n", "\\n", ". ",
" ", ""]`` by default - and at each level:

1. Splits the input on the highest-priority separator that appears.
2. Any piece still exceeding ``chunk_size`` is recursed with the
   remaining lower-priority separators.
3. Bounded pieces are greedily merged into chunks as close to (but not
   exceeding) ``chunk_size`` as possible, honouring ``chunk_overlap``
   between neighbouring chunks.

The ``""`` sentinel at the tail is the absolute fallback: when every
higher separator has failed to fit a chunk, the chunk is hard-sliced
character-by-character.
"""

from __future__ import annotations

from typing import Final

_DEFAULT_SEPARATORS: Final[tuple[str, ...]] = ("\n\n", "\n", ". ", " ", "")


def split_text(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    separators: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """Split ``text`` into chunks bounded by ``chunk_size``.

    Args:
        text: Input text.
        chunk_size: Maximum chunk length in characters. Must be > 0.
        chunk_overlap: Characters shared between neighbouring chunks.
            Must be >= 0 and strictly less than ``chunk_size``.
        separators: Priority-ordered separators. The last entry should
            be ``""`` to guarantee termination on pathological inputs.
            When ``None``, a sensible default is used.

    Returns:
        List of non-empty chunks in original order.

    Raises:
        ValueError: if ``chunk_size`` or ``chunk_overlap`` are invalid.
    """
    if chunk_size <= 0:
        msg = f"chunk_size must be > 0, got {chunk_size}"
        raise ValueError(msg)
    if chunk_overlap < 0:
        msg = f"chunk_overlap must be >= 0, got {chunk_overlap}"
        raise ValueError(msg)
    if chunk_overlap >= chunk_size:
        msg = f"chunk_overlap ({chunk_overlap}) must be < chunk_size ({chunk_size})"
        raise ValueError(msg)
    if not text:
        return []
    seps = tuple(separators) if separators else _DEFAULT_SEPARATORS
    bounded = _bound_pieces(
        text, seps, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
    )
    return _merge(
        bounded, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
    )


def _bound_pieces(
    text: str,
    separators: tuple[str, ...],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Return ``text`` split into pieces each no larger than ``chunk_size``."""
    separator, remainder = _pick_separator(text, separators)
    result: list[str] = []
    for piece in _split_on(text, separator):
        if not piece:
            continue
        if len(piece) <= chunk_size:
            result.append(piece)
        elif remainder:
            result.extend(
                _bound_pieces(
                    piece, remainder,
                    chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                ),
            )
        else:
            result.extend(_hard_slice(piece, chunk_size, chunk_overlap))
    return result


def _pick_separator(
    text: str,
    separators: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    """Return the first separator present in ``text`` plus the tail.

    The final ``""`` sentinel always matches, guaranteeing termination.
    """
    for idx, sep in enumerate(separators):
        if sep == "" or sep in text:
            return sep, separators[idx + 1 :]
    return "", ()


def _split_on(text: str, separator: str) -> list[str]:
    """Split ``text`` on ``separator``, keeping the separator attached left."""
    if separator == "":
        return list(text)
    parts = text.split(separator)
    out: list[str] = []
    last = len(parts) - 1
    for idx, part in enumerate(parts):
        out.append(part + separator if idx < last else part)
    return out


def _hard_slice(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Slice ``text`` into ``chunk_size``-sized windows with ``chunk_overlap``."""
    step = chunk_size - chunk_overlap
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += step
    return chunks


def _merge(
    pieces: list[str],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Greedily combine pieces into chunks of size <= ``chunk_size``."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for piece in pieces:
        piece_len = len(piece)
        if current and current_len + piece_len > chunk_size:
            chunks.append("".join(current))
            current, current_len = _seed_with_overlap(current, chunk_overlap)
        current.append(piece)
        current_len += piece_len
    if current:
        chunks.append("".join(current))
    return [c for c in chunks if c]


def _seed_with_overlap(
    prior: list[str],
    chunk_overlap: int,
) -> tuple[list[str], int]:
    """Take the tail of ``prior`` up to ``chunk_overlap`` chars as overlap."""
    if chunk_overlap == 0:
        return [], 0
    seed: list[str] = []
    total = 0
    for piece in reversed(prior):
        if total + len(piece) > chunk_overlap and seed:
            break
        seed.insert(0, piece)
        total += len(piece)
        if total >= chunk_overlap:
            break
    return seed, total
