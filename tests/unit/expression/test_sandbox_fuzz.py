"""Hypothesis-driven fuzzing of the expression sandbox.

The hardcoded corpus in :mod:`test_sandbox_bypass_corpus` locks in *known*
bypass shapes. This module searches the space around them: every test
uses :mod:`hypothesis` to generate adversarial expression sources that
stitch together attribute walks, format-string tricks, and builtin calls
— then asserts that **only** :class:`ExpressionError` (or one of its
subclasses) ever escapes. An unexpected exception class is the signal
that some escape route exists we have not yet closed.

These tests do not try to prove the sandbox is correct — they are a
shallow regression net that catches obvious regressions when somebody
later relaxes the guard "just a little".

The test budget is deliberately small (``max_examples=200``) so the
suite stays fast; CI may override with ``WEFTLYFLOW_FUZZ_EXAMPLES``.
"""

from __future__ import annotations

import contextlib
import os

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from weftlyflow.expression import clear_cache, resolve
from weftlyflow.expression.errors import ExpressionError

_MAX_EXAMPLES: int = int(os.getenv("WEFTLYFLOW_FUZZ_EXAMPLES", "200"))

# Primitives the fuzzer can reference. These are all reachable inside the
# sandbox (``isinstance``, ``str``, etc.) and are interesting precisely
# because they give the fuzzer real objects to attack.
_REFERENCES: list[str] = [
    "1",
    '""',
    "[]",
    "{}",
    "()",
    "(lambda: 1)",
    "str",
    "int",
    "list",
    "dict",
    "isinstance",
    "len",
    "range(3)",
    "sorted([3,1,2])",
]

# Attribute names the fuzzer is allowed to traverse. Both benign and
# dangerous names are included — the point of fuzzing is to confirm that
# the dangerous ones are rejected no matter how they are reached.
_ATTRS: list[str] = [
    # Dunder
    "__class__",
    "__bases__",
    "__mro__",
    "__subclasses__",
    "__globals__",
    "__code__",
    "__init__",
    "__dict__",
    "__module__",
    # Non-dunder escape primitives
    "mro",
    "format",
    "format_map",
    # Ordinary benign attributes (should never blow up beyond ExpressionError)
    "real",
    "imag",
    "append",
    "keys",
    "values",
    "items",
    "upper",
    "lower",
]


@st.composite
def _attr_walks(draw: st.DrawFn) -> str:
    """Generate ``<ref>.<attr>(.<attr>)*`` expressions of random depth."""
    base = draw(st.sampled_from(_REFERENCES))
    depth = draw(st.integers(min_value=1, max_value=4))
    attrs = [draw(st.sampled_from(_ATTRS)) for _ in range(depth)]
    return base + "".join(f".{a}" for a in attrs)


@st.composite
def _format_strings(draw: st.DrawFn) -> str:
    """Generate ``"{...}".format(<ref>)`` shapes — the 8a regression class."""
    attrs = draw(st.lists(st.sampled_from(_ATTRS), min_size=1, max_size=3))
    spec = "{0" + "".join(f".{a}" for a in attrs) + "}"
    ref = draw(st.sampled_from(_REFERENCES))
    method = draw(st.sampled_from(["format", "format_map"]))
    if method == "format_map":
        return f'"{spec}".format_map({{"0": {ref}}})'
    return f'"{spec}".format({ref})'


@st.composite
def _subscript_chains(draw: st.DrawFn) -> str:
    """Generate ``<ref>[<index>]`` walks — tests _getitem_ surface."""
    base = draw(st.sampled_from(_REFERENCES))
    depth = draw(st.integers(min_value=1, max_value=3))
    parts = [base]
    for _ in range(depth):
        idx = draw(st.one_of(st.integers(min_value=0, max_value=5), st.just('"x"')))
        parts.append(f"[{idx}]")
    return "".join(parts)


_ADVERSARIAL = st.one_of(_attr_walks(), _format_strings(), _subscript_chains())


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_cache()


@settings(
    max_examples=_MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=_ADVERSARIAL)
def test_adversarial_payloads_never_escape_the_error_hierarchy(payload: str) -> None:
    """No adversarial payload may leak past :class:`ExpressionError`.

    A legitimate expression may evaluate to a value; a malformed or
    dangerous one must raise something in the ``ExpressionError``
    hierarchy. Anything else — a ``SystemExit``, a plain ``OSError``
    from reaching IO, or a successful evaluation that yields a
    walkable ``type`` object — is a sandbox regression.
    """
    template = "{{ " + payload + " }}"
    try:
        result = resolve(template, {})
    except ExpressionError:
        return  # Expected path.
    # If evaluation "succeeded", the result must be a plain data value —
    # never a type object, module, frame, or callable-with-__globals__.
    assert not isinstance(result, type), f"leaked type object: {result!r}"
    assert not callable(result) or _is_safe_callable(result), (
        f"leaked callable with rich surface: {result!r}"
    )


def _is_safe_callable(obj: object) -> bool:
    """True when ``obj`` is a benign builtin/method and not a user function.

    User-defined functions expose ``__globals__``; blocking that here
    would have flagged the ``"{0.__globals__}".format(lambda: 1)`` bug
    earlier. Builtin methods don't have ``__globals__``, so they're
    treated as harmless for the purposes of this assertion.
    """
    return not hasattr(obj, "__globals__")


@settings(
    max_examples=_MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    name=st.text(
        alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd"], whitelist_characters="_"),
        min_size=1,
        max_size=20,
    ),
)
def test_arbitrary_attribute_access_never_crashes_the_guard(name: str) -> None:
    """The guard must classify any attribute name without raising non-``ExpressionError``.

    A defensive regression: if someone introduces a ``TypeError`` in
    ``_guarded_getattr`` by type-annotating too loosely, fuzz traffic
    would surface it before production does.
    """
    template = "{{ (1)." + name + " }}" if name.isidentifier() else '{{ 1 }}'
    with contextlib.suppress(ExpressionError):
        resolve(template, {})
