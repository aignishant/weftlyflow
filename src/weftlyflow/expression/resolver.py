"""Top-level expression resolver.

Thin glue over :mod:`tokenizer`, :mod:`sandbox`, and :mod:`proxies`. Two
public entry points:

* :func:`resolve` — evaluate a single template string.
* :func:`resolve_tree` — walk a nested ``dict``/``list`` parameter tree and
  replace any string value that contains ``{{`` with its evaluated form.

Semantics — matching the spec in IMPLEMENTATION_BIBLE.md §10.3:

* A template that is exactly one ``{{ ... }}`` chunk returns the raw
  evaluated value (``int``, ``list``, ``None``, ...).
* A template that mixes literal text with expressions returns a ``str``,
  concatenating literal text with ``str(value)`` of each chunk.
* A template with no expressions is returned unchanged.

Compiled expressions are cached per-source so tight loops over an
expression-heavy workflow don't re-parse the same chunk on each item.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from weftlyflow.expression.sandbox import compile_expression, evaluate
from weftlyflow.expression.tokenizer import (
    ExpressionChunk,
    LiteralChunk,
    contains_expression,
    is_single_expression,
    tokenize,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


_COMPILE_CACHE_SIZE: int = 1024


@lru_cache(maxsize=_COMPILE_CACHE_SIZE)
def _compile_cached(source: str) -> Any:
    return compile_expression(source)


def resolve(template: Any, proxies: Mapping[str, Any]) -> Any:
    """Return the resolved value for ``template``.

    Non-string inputs pass through unchanged — callers often feed arbitrary
    parameter values (numbers, booleans, pre-built dicts) and the resolver
    must not destroy them.
    """
    if not isinstance(template, str):
        return template
    if not contains_expression(template):
        return template

    chunks = tokenize(template)
    if is_single_expression(chunks):
        chunk = chunks[0]
        assert isinstance(chunk, ExpressionChunk)
        return evaluate(_compile_cached(chunk.source), dict(proxies))

    parts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, LiteralChunk):
            parts.append(chunk.text)
        else:
            value = evaluate(_compile_cached(chunk.source), dict(proxies))
            parts.append("" if value is None else str(value))
    return "".join(parts)


def resolve_tree(tree: Any, proxies: Mapping[str, Any]) -> Any:
    """Recursively resolve every string in a nested parameter structure.

    Lists and tuples are walked; dicts are walked key-by-key. Any other
    type is returned as-is. The structure is rebuilt — we never mutate the
    caller's original object.
    """
    if isinstance(tree, str):
        return resolve(tree, proxies)
    if isinstance(tree, dict):
        return {key: resolve_tree(value, proxies) for key, value in tree.items()}
    if isinstance(tree, list):
        return [resolve_tree(item, proxies) for item in tree]
    if isinstance(tree, tuple):
        return tuple(resolve_tree(item, proxies) for item in tree)
    return tree


def clear_cache() -> None:
    """Empty the compile cache. Useful in tests that mutate expression bodies."""
    _compile_cached.cache_clear()
