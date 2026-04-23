"""Child process entry point for :mod:`weftlyflow.worker.sandbox_runner`.

Runs as ``python -m weftlyflow.worker.sandbox_child`` inside a fresh
interpreter with resource limits already applied by the parent. Reads a
single JSON request from stdin, executes the snippet under
:mod:`RestrictedPython` in ``exec`` mode, and writes a single JSON
response to stdout. No IO, no imports from the rest of Weftlyflow — the
surface is deliberately tiny.

Protocol::

    REQUEST  = {"code": "<snippet>", "items": [{"json": ..., ...}, ...]}
    RESPONSE = {"ok": true,  "items": [...]}                # success
             | {"ok": false, "error": "<message>"}          # failure

Exit codes::

    0  — response written to stdout (``ok`` may still be false)
    1  — unrecoverable error before stdout could be written
"""

from __future__ import annotations

import builtins
import json
import sys
from typing import Any

from RestrictedPython import compile_restricted_exec, safe_builtins

_ALLOWED_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        "len", "range", "sum", "min", "max", "abs", "round",
        "str", "int", "float", "bool", "list", "dict", "tuple", "set",
        "sorted", "reversed", "enumerate", "zip",
        "any", "all", "map", "filter",
        "isinstance", "issubclass",
        "True", "False", "None",
        "print",  # captured via the child's stdout; harmless
    },
)

_FORBIDDEN_BUILTINS: frozenset[str] = frozenset(
    {
        "type", "setattr", "delattr", "__build_class__",
        "open", "compile", "exec", "eval", "__import__",
        "_getattr_", "globals", "locals", "vars", "dir", "getattr",
        "input", "breakpoint", "help",
    },
)

_BLOCKED_ATTR_NAMES: frozenset[str] = frozenset({"format_map", "mro"})


def _guarded_getattr(obj: Any, name: str, *default: Any) -> Any:
    if not isinstance(name, str):
        msg = f"attribute name must be str, not {type(name).__name__}"
        raise PermissionError(msg)
    if name.startswith("_") or name.endswith("_"):
        msg = f"access to {name!r} is not permitted in code node snippets"
        raise PermissionError(msg)
    if name in _BLOCKED_ATTR_NAMES:
        msg = f"access to {name!r} is not permitted in code node snippets"
        raise PermissionError(msg)
    if name == "format" and isinstance(obj, str):
        msg = "str.format is not permitted in code node snippets"
        raise PermissionError(msg)
    if default:
        return getattr(obj, name, default[0])
    return getattr(obj, name)


def _build_builtins() -> dict[str, Any]:
    base = dict(safe_builtins)
    for name in _ALLOWED_BUILTIN_NAMES:
        if name in base:
            continue
        if hasattr(builtins, name):
            base[name] = getattr(builtins, name)
    for banned in _FORBIDDEN_BUILTINS:
        base.pop(banned, None)
    return base


def _run_snippet(code: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compile + exec ``code`` with ``items`` bound; return the new items list.

    The snippet contract matches the Code node's published surface: the
    ``items`` variable is a list of dicts, and the snippet either mutates
    it in place or rebinds it. Whatever is in ``items`` at the end is the
    result.
    """
    result = compile_restricted_exec(code, filename="<weftlyflow-code>")
    if result.errors:
        joined = "; ".join(result.errors)
        msg = f"code rejected by sandbox: {joined}"
        raise PermissionError(msg)
    if result.code is None:
        msg = "code failed to compile"
        raise SyntaxError(msg)

    globals_dict: dict[str, Any] = {
        "__builtins__": _build_builtins(),
        "_getattr_": _guarded_getattr,
        "_getitem_": lambda obj, idx: obj[idx],
        "_getiter_": iter,
        "_write_": lambda obj: obj,
        "_inplacevar_": _inplacevar,
        "items": [dict(it) for it in items],
    }
    exec(result.code, globals_dict)
    out = globals_dict.get("items", [])
    if not isinstance(out, list):
        msg = "snippet must leave `items` bound to a list of dicts"
        raise TypeError(msg)
    return [dict(it) if isinstance(it, dict) else {"value": it} for it in out]


def _inplacevar(op: str, x: Any, y: Any) -> Any:
    """Minimal in-place operator support — needed for ``x += 1`` patterns."""
    if op == "+=":
        return x + y
    if op == "-=":
        return x - y
    if op == "*=":
        return x * y
    msg = f"in-place operator {op!r} is not permitted"
    raise PermissionError(msg)


def main() -> int:
    """Read one JSON request from stdin, run the snippet, write one JSON response.

    Returns ``0`` whenever a response was written (even an ``ok: false``
    payload), ``1`` only when stdout itself is unwritable.
    """
    try:
        raw = sys.stdin.read()
        request = json.loads(raw)
        code = request["code"]
        items = request.get("items", [])
        out_items = _run_snippet(code, items)
        sys.stdout.write(json.dumps({"ok": True, "items": out_items}))
        return 0
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        try:
            sys.stdout.write(json.dumps({"ok": False, "error": message}))
        except Exception:
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
