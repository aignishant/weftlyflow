"""RestrictedPython compile + evaluate.

Two layers of defence:

1. **Compile time** — :func:`compile_expression` runs the source through
   ``RestrictedPython.compile_restricted_eval`` which rejects anything
   dangerous at parse time (``__import__``, attribute access on dunder
   names, unpacking tricks, etc.).
2. **Runtime** — :func:`evaluate` calls the compiled code against a
   hard-coded globals dict that exposes only the intentional builtins plus
   whatever proxies the caller provides.

Python's grammar does not accept ``$`` in identifiers, so we textually
rewrite ``$json`` → ``DOLLAR_json`` (and the same for every other proxy)
before handing the source to the compiler. The caller's globals dict is
rewritten the same way so the bound names line up.

There is no runtime CPU cap in Phase 4 — a malicious expression can still
spin-loop. That's acceptable for user-authored templates; runtime
enforcement is layered in Phase 6 via the existing sandbox subprocess used
by the Code node. For now we rely on a soft wall-clock timeout monitored
by the caller.

This module never accesses the database and does not know about
``ExecutionContext``. The resolver builds the proxies and hands them in.
"""

from __future__ import annotations

import builtins as _python_builtins
import re
from typing import Any

from RestrictedPython import compile_restricted_eval, safe_builtins
from RestrictedPython.Eval import default_guarded_getattr, default_guarded_getitem

from weftlyflow.expression.errors import (
    ExpressionEvalError,
    ExpressionSecurityError,
    ExpressionSyntaxError,
)

# Weftlyflow expressions use ``$name`` for proxies — replace with a Python-valid
# identifier before compiling. The prefix is intentionally unusual so user
# code cannot accidentally collide with it.
_DOLLAR_PREFIX: str = "DOLLAR_"
_DOLLAR_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _rewrite_dollars(source: str) -> str:
    return _DOLLAR_RE.sub(lambda m: f"{_DOLLAR_PREFIX}{m.group(1)}", source)


def rewrite_proxy_keys(proxies: dict[str, Any]) -> dict[str, Any]:
    """Translate ``$name`` keys to the compiled form used by :func:`evaluate`."""
    out: dict[str, Any] = {}
    for key, value in proxies.items():
        if key.startswith("$"):
            out[f"{_DOLLAR_PREFIX}{key[1:]}"] = value
        else:
            out[key] = value
    return out

# Callables from the Python builtins allow-list. Names chosen to match the
# n8n mental model while staying inside pure, side-effect-free helpers.
_ALLOWED_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        "len", "range", "sum", "min", "max", "abs", "round",
        "str", "int", "float", "bool", "list", "dict", "tuple", "set",
        "sorted", "reversed", "enumerate", "zip",
        "any", "all", "map", "filter",
        "isinstance", "type",
        "True", "False", "None",
    },
)


def _build_builtins_dict() -> dict[str, Any]:
    base = dict(safe_builtins)
    for name in _ALLOWED_BUILTIN_NAMES:
        if name in base:
            continue
        if hasattr(_python_builtins, name):
            base[name] = getattr(_python_builtins, name)
    # Remove anything we don't want even if safe_builtins had it.
    for banned in ("open", "compile", "exec", "eval", "__import__"):
        base.pop(banned, None)
    return base


_SAFE_BUILTINS: dict[str, Any] = _build_builtins_dict()


def compile_expression(source: str) -> Any:
    """Compile ``source`` in restricted mode; return the code object.

    The ``$name`` proxy syntax is textually rewritten before compilation so
    CPython's parser accepts it.

    Raises:
        ExpressionSyntaxError: on parse failure (malformed Python).
        ExpressionSecurityError: when RestrictedPython rejects the code.
    """
    rewritten = _rewrite_dollars(source)
    result = compile_restricted_eval(rewritten, filename="<weftlyflow-expression>")
    if result.errors:
        msg = f"expression rejected: {'; '.join(result.errors)} — source={source!r}"
        raise ExpressionSecurityError(msg)
    if result.code is None:
        msg = f"expression failed to compile: {source!r}"
        raise ExpressionSyntaxError(msg)
    return result.code


def evaluate(code: Any, proxies: dict[str, Any]) -> Any:
    """Run ``code`` against ``proxies`` and return the Python value.

    The globals dict is rebuilt on every call so the caller's proxies can
    mutate safely without leaking between evaluations.
    """
    globals_dict: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "_getattr_": default_guarded_getattr,
        "_getitem_": default_guarded_getitem,
        "_getiter_": iter,
        "_unpack_sequence_": _unpack_sequence,
        "_iter_unpack_sequence_": _unpack_sequence,
    }
    globals_dict.update(rewrite_proxy_keys(proxies))
    try:
        return eval(code, globals_dict, {})  # nosec B307 — restricted compile gates input.
    except ExpressionSyntaxError:
        raise
    except Exception as exc:
        msg = f"expression failed at runtime: {type(exc).__name__}: {exc}"
        raise ExpressionEvalError(msg) from exc


def _unpack_sequence(it: Any, *_args: Any, **_kwargs: Any) -> Any:
    return it
