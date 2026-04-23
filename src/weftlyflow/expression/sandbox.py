"""RestrictedPython compile + evaluate with a strict runtime guard.

Two layers of defence:

1. **Compile time** — :func:`compile_expression` runs the source through
   ``RestrictedPython.compile_restricted_eval`` which rejects any *source-level*
   dunder attribute access (``x.__class__``, ``f.__globals__``, ...) at parse
   time.
2. **Runtime** — :func:`evaluate` executes the compiled code against a
   hand-picked globals dict. Every attribute access compiled from ``x.y``
   source is routed through :func:`_guarded_getattr`, which blocks:

   * any name starting **or ending** with an underscore (catches every dunder
     and every private convention);
   * the ``mro`` method on :class:`type` objects, which would otherwise expose
     ``[int, object]`` and allow escape through ``object.mro`` walks;
   * ``format`` / ``format_map`` on :class:`str`, because those perform
     ``__getattribute__`` on their arguments internally and are not routed
     through ``_getattr_`` — an attacker would otherwise write
     ``"{0.__globals__}".format(lambda: 1)`` and reach the real
     ``__builtins__``.

We also scrub :data:`RestrictedPython.safe_builtins` of ``type``, ``setattr``,
``delattr``, and ``__build_class__`` before exposing it; each of those is a
documented escape primitive.

Python's grammar does not accept ``$`` in identifiers, so we textually
rewrite ``$json`` → ``DOLLAR_json`` (and the same for every other proxy)
before handing the source to the compiler. The caller's globals dict is
rewritten the same way so the bound names line up.

Wall-clock enforcement is done by :func:`evaluate`'s caller — the Celery
worker sets ``task_soft_time_limit`` and the synchronous resolver wraps the
call in a ``concurrent.futures`` deadline (see
:mod:`weftlyflow.expression.resolver`).

This module never accesses the database and does not know about
``ExecutionContext``. The resolver builds the proxies and hands them in.
"""

from __future__ import annotations

import builtins as _python_builtins
import re
from typing import Any

from RestrictedPython import compile_restricted_eval, safe_builtins
from RestrictedPython.Eval import default_guarded_getitem

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


# Callables from the Python builtins allow-list. ``type`` is deliberately
# excluded — it lets callers reach ``type(x).mro()`` → ``object`` and walk
# subclasses. ``isinstance`` / ``issubclass`` are safe because they accept
# types but do not return them in a walkable form.
_ALLOWED_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        "len", "range", "sum", "min", "max", "abs", "round",
        "str", "int", "float", "bool", "list", "dict", "tuple", "set",
        "sorted", "reversed", "enumerate", "zip",
        "any", "all", "map", "filter",
        "isinstance", "issubclass",
        "True", "False", "None",
    },
)

# Names that ``safe_builtins`` exposes by default but which are known escape
# primitives and must never reach expression code.
_FORBIDDEN_BUILTINS: frozenset[str] = frozenset(
    {
        "type",           # reaches ``object`` via ``type(x).mro()``
        "setattr",        # mutates arbitrary objects
        "delattr",        # mutates arbitrary objects
        "__build_class__",  # constructs metaclasses
        "open", "compile", "exec", "eval", "__import__",  # direct IO / RCE
        "_getattr_",      # RestrictedPython placeholder; we bind our own
        "globals", "locals", "vars", "dir",  # reflect module internals
        "getattr",        # bypasses ``_getattr_`` routing
    },
)

# Method names that must never be reached on *any* object. ``format`` and
# ``format_map`` on strings do internal ``__getattribute__`` walks that the
# compile-time dunder filter cannot see; blocking the bound-method access
# closes that door. ``mro`` is the last non-dunder route from a ``type``
# instance to ``object`` and its subclasses.
_BLOCKED_ATTR_NAMES: frozenset[str] = frozenset(
    {
        "format_map",
        "mro",
    },
)


def _build_builtins_dict() -> dict[str, Any]:
    base = dict(safe_builtins)
    for name in _ALLOWED_BUILTIN_NAMES:
        if name in base:
            continue
        if hasattr(_python_builtins, name):
            base[name] = getattr(_python_builtins, name)
    for banned in _FORBIDDEN_BUILTINS:
        base.pop(banned, None)
    return base


_SAFE_BUILTINS: dict[str, Any] = _build_builtins_dict()


def _guarded_getattr(obj: Any, name: str, *default: Any) -> Any:
    """Attribute lookup router installed as ``_getattr_`` in the sandbox.

    RestrictedPython rewrites every ``x.y`` in restricted source to
    ``_getattr_(x, 'y')``, so this function gates every dotted access a
    template author can write. We reject dunder-style names and a short list
    of attribute names that are reachable via non-dunder syntax but expose
    escape primitives (``format``/``format_map`` on :class:`str`, ``mro`` on
    any type).

    Raises:
        ExpressionSecurityError: when the attribute name is on the denylist.
    """
    if not isinstance(name, str):
        msg = f"attribute name must be str, not {type(name).__name__}"
        raise ExpressionSecurityError(msg)
    if name.startswith("_") or name.endswith("_"):
        msg = f"access to {name!r} is not permitted in expressions"
        raise ExpressionSecurityError(msg)
    if name in _BLOCKED_ATTR_NAMES:
        msg = f"access to {name!r} is not permitted in expressions"
        raise ExpressionSecurityError(msg)
    # ``format`` is a legitimate method on domain types (e.g. WeftlyflowDateTime)
    # but on :class:`str` it is an escape primitive — block only that case.
    if name == "format" and isinstance(obj, str):
        msg = "str.format is not permitted in expressions"
        raise ExpressionSecurityError(msg)
    if default:
        return getattr(obj, name, default[0])
    return getattr(obj, name)


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
        "_getattr_": _guarded_getattr,
        "_getitem_": default_guarded_getitem,
        "_getiter_": iter,
        "_unpack_sequence_": _unpack_sequence,
        "_iter_unpack_sequence_": _unpack_sequence,
    }
    globals_dict.update(rewrite_proxy_keys(proxies))
    try:
        return eval(code, globals_dict, {})  # nosec B307 — restricted compile + guarded getattr gate input.
    except ExpressionSecurityError:
        raise
    except ExpressionSyntaxError:
        raise
    except Exception as exc:
        msg = f"expression failed at runtime: {type(exc).__name__}: {exc}"
        raise ExpressionEvalError(msg) from exc


def _unpack_sequence(it: Any, *_args: Any, **_kwargs: Any) -> Any:
    return it
