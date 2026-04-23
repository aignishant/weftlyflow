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

import concurrent.futures
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from weftlyflow.config import get_settings
from weftlyflow.expression.errors import ExpressionTimeoutError
from weftlyflow.expression.sandbox import compile_expression, evaluate
from weftlyflow.expression.tokenizer import (
    ExpressionChunk,
    LiteralChunk,
    contains_expression,
    is_single_expression,
    tokenize,
)
from weftlyflow.observability import metrics

if TYPE_CHECKING:
    from collections.abc import Mapping


_COMPILE_CACHE_SIZE: int = 1024

# Dedicated executor for expression evaluation. A single shared pool means
# runaway expressions do not multiply into unbounded thread creation — at
# worst they queue. Daemon threads so interpreter shutdown is not blocked.
_EVAL_POOL: concurrent.futures.ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="weftlyflow-expr",
)


def _evaluate_with_timeout(code: Any, proxies: dict[str, Any]) -> Any:
    """Run :func:`evaluate` under the configured wall-clock budget.

    On timeout we raise :class:`ExpressionTimeoutError`; the worker thread
    keeps running in the pool until it either finishes or is torn down with
    the process, but the caller is unblocked.

    This is a soft guard — a truly malicious expression can still burn a
    worker thread until Celery's hard ``task_time_limit`` kills the
    process. Layered defence.
    """
    timeout = get_settings().expression_timeout_seconds
    future = _EVAL_POOL.submit(evaluate, code, proxies)
    try:
        value = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError as exc:
        metrics.expression_evaluations_total.labels(outcome="timeout").inc()
        msg = f"expression exceeded {timeout}s wall-clock budget"
        raise ExpressionTimeoutError(msg) from exc
    except Exception:
        metrics.expression_evaluations_total.labels(outcome="error").inc()
        raise
    metrics.expression_evaluations_total.labels(outcome="success").inc()
    return value


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
        return _evaluate_with_timeout(_compile_cached(chunk.source), dict(proxies))

    parts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, LiteralChunk):
            parts.append(chunk.text)
        else:
            value = _evaluate_with_timeout(_compile_cached(chunk.source), dict(proxies))
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
