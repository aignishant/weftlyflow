"""Regression corpus for known RestrictedPython sandbox-escape payloads.

Every payload in :data:`_ATTACK_PAYLOADS` was either confirmed reachable
against a previous Weftlyflow expression sandbox, or appears in public
write-ups of RestrictedPython bypasses. The fix lives in
:mod:`weftlyflow.expression.sandbox` — if any of these ever stop raising
:class:`ExpressionSecurityError` (or one of its close relatives), a
regression has landed.

The intent is not to prove the sandbox is correct by construction — that is
impossible — but to lock in the closed doors so nobody reopens one by
accident.
"""

from __future__ import annotations

import pytest

from weftlyflow.expression import clear_cache, resolve
from weftlyflow.expression.errors import (
    ExpressionError,
    ExpressionEvalError,
    ExpressionSecurityError,
)

# Each payload is the raw expression body; the test wraps it in ``{{ }}``.
# Any exception from the :class:`ExpressionError` hierarchy counts as
# "blocked" — we intentionally do not assert a single exception class
# because some payloads die at compile time (``ExpressionSecurityError``)
# and some at runtime (``ExpressionEvalError``), and that split is an
# implementation detail we must be free to move.
_ATTACK_PAYLOADS: list[str] = [
    # --- str.format attribute-walk bypasses ------------------------------
    '"{0.__globals__}".format(lambda: 1)',
    '"{0.__globals__[__builtins__]}".format(lambda: 1)',
    '"{0.__class__.__mro__[1].__subclasses__}".format(1)',
    '"{0.__self__}".format([].append)',
    '"{0.__mro__}".format(type(1))',
    '"{a.__class__}".format_map({"a": 1})',
    # --- type().mro() walks to object ------------------------------------
    "list.mro",
    "list.mro()",
    "dict.mro()[1]",
    "int.mro",
    "str.mro()",
    "list.mro()[1].mro",
    # --- direct dunder access (should die at compile) --------------------
    "(1).__class__",
    "().__class__.__bases__",
    "[].__class__.__mro__",
    "type(1).__mro__",
    "type(1).__subclasses__()",
    "(lambda: 1).__globals__",
    "(lambda: 1).__code__",
    # --- builtins escape primitives that must be absent ------------------
    "__import__",
    "__import__('os')",
    "open('/etc/passwd')",
    "exec('print(1)')",
    "eval('1+1')",
    "compile('1', 'x', 'eval')",
    "globals()",
    "locals()",
    "vars(1)",
    "dir(1)",
    "getattr(1, 'real')",
    "setattr(object(), 'x', 1)",
    "delattr(object(), 'x')",
    # --- type-metaclass construction tricks ------------------------------
    'type("C", (int,), {})',
    'type(type)("x", (), {"a": 1})',
    # --- format-map / % format sanity ------------------------------------
    # ``%`` format only does dict-key lookup, no attribute walk — these
    # must remain blocked because RestrictedPython sees attr dunders at
    # parse time, and the runtime guard blocks the rest.
    '"%s" % (lambda: 1).__code__',
    # --- f-string attribute walks (caught at compile by dunder rule) -----
    'f"{(lambda: 1).__globals__}"',
    'f"{(1).__class__}"',
]


@pytest.fixture(autouse=True)
def _reset_expression_cache() -> None:
    """Keep the compile cache from leaking state between parametrised cases."""
    clear_cache()


@pytest.mark.parametrize("payload", _ATTACK_PAYLOADS)
def test_sandbox_rejects_known_bypass(payload: str) -> None:
    """Every entry in the bypass corpus must raise an ExpressionError."""
    template = "{{ " + payload + " }}"
    proxies: dict[str, object] = {}
    with pytest.raises(ExpressionError):
        resolve(template, proxies)


def test_format_still_works_on_domain_datetime() -> None:
    """``$now.format("%Y")`` must remain legal — only ``str.format`` is blocked.

    The guard discriminates on object type: strings cannot invoke
    ``format``, but domain objects like :class:`WeftlyflowDateTime` that
    implement a legitimate ``format`` method are untouched.
    """
    from weftlyflow.expression.proxies import WeftlyflowDateTime

    proxies = {"$now": WeftlyflowDateTime.now()}
    # Should not raise — this is the user-facing happy path.
    out = resolve('{{ $now.format("%Y") }}', proxies)
    assert isinstance(out, str)
    assert len(out) == 4


def test_str_format_is_blocked_even_with_benign_args() -> None:
    """str.format is unreachable regardless of the format argument."""
    with pytest.raises(ExpressionSecurityError):
        resolve('{{ "hi {}".format("x") }}', {})


def test_runtime_errors_still_bubble_as_eval_error() -> None:
    """Confirm we did not accidentally swallow ordinary runtime errors."""
    with pytest.raises(ExpressionEvalError):
        resolve("{{ 1 / 0 }}", {})


def test_long_running_expression_times_out() -> None:
    """A pathological expression hits the wall-clock guard, not a deadlock.

    Without the timeout, ``{{ sum(range(10**8)) }}`` pins a worker until
    Celery's hard limit fires. With the guard it fails fast with a
    ``ExpressionTimeoutError``.
    """
    from weftlyflow.config import get_settings
    from weftlyflow.expression.errors import ExpressionTimeoutError

    # Drop the budget to keep the test fast; restore via cache_clear.
    settings = get_settings()
    original = settings.expression_timeout_seconds
    object.__setattr__(settings, "expression_timeout_seconds", 0.05)
    try:
        with pytest.raises(ExpressionTimeoutError):
            resolve("{{ sum(range(10**8)) }}", {})
    finally:
        object.__setattr__(settings, "expression_timeout_seconds", original)
