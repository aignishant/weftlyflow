"""Predicate operators used by branching nodes (``If``, later ``Switch``/``Filter``).

Factored out so the exact operator semantics are declared in exactly one
place. New operators added here become available to every node that imports
:func:`evaluate_predicate`.

Phase-1 scope: literal value comparisons only. The expression engine in
Phase 4 will feed its resolved left/right values into :func:`evaluate_predicate`
unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final, Literal, cast

PredicateOperator = Literal[
    "equals",
    "not_equals",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_empty",
    "is_not_empty",
    "is_true",
    "is_false",
]

PREDICATE_OPERATORS: Final[tuple[PredicateOperator, ...]] = (
    "equals",
    "not_equals",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_empty",
    "is_not_empty",
    "is_true",
    "is_false",
)


def evaluate_predicate(
    left: Any,
    operator: PredicateOperator,
    right: Any = None,
) -> bool:
    """Return ``True`` when ``left <operator> right`` holds.

    Unary operators (``is_empty``, ``is_not_empty``, ``is_true``, ``is_false``)
    ignore ``right``.

    Example:
        >>> evaluate_predicate("hello", "contains", "ell")
        True
        >>> evaluate_predicate([], "is_empty")
        True
    """
    handler = _HANDLERS.get(operator)
    if handler is None:
        msg = f"unknown predicate operator: {operator!r}"
        raise ValueError(msg)
    return handler(left, right)


def _equals(left: Any, right: Any) -> bool:
    # ``Any == Any`` is Any under --strict; cast narrows without runtime overhead.
    return cast(bool, left == right)


def _not_equals(left: Any, right: Any) -> bool:
    return cast(bool, left != right)


def _greater_than(left: Any, right: Any) -> bool:
    return bool(left > right)


def _greater_than_or_equal(left: Any, right: Any) -> bool:
    return bool(left >= right)


def _less_than(left: Any, right: Any) -> bool:
    return bool(left < right)


def _less_than_or_equal(left: Any, right: Any) -> bool:
    return bool(left <= right)


def _contains(left: Any, right: Any) -> bool:
    if left is None:
        return False
    return right in left


def _not_contains(left: Any, right: Any) -> bool:
    return not _contains(left, right)


def _starts_with(left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return left.startswith(right)
    return False


def _ends_with(left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return left.endswith(right)
    return False


def _is_empty(left: Any, _right: Any) -> bool:
    if left is None:
        return True
    try:
        return len(left) == 0
    except TypeError:
        return False


def _is_not_empty(left: Any, right: Any) -> bool:
    return not _is_empty(left, right)


def _is_true(left: Any, _right: Any) -> bool:
    return bool(left) is True


def _is_false(left: Any, _right: Any) -> bool:
    return bool(left) is False


_Handler = Callable[[Any, Any], bool]

_HANDLERS: Final[dict[PredicateOperator, _Handler]] = {
    "equals": _equals,
    "not_equals": _not_equals,
    "greater_than": _greater_than,
    "greater_than_or_equal": _greater_than_or_equal,
    "less_than": _less_than,
    "less_than_or_equal": _less_than_or_equal,
    "contains": _contains,
    "not_contains": _not_contains,
    "starts_with": _starts_with,
    "ends_with": _ends_with,
    "is_empty": _is_empty,
    "is_not_empty": _is_not_empty,
    "is_true": _is_true,
    "is_false": _is_false,
}
