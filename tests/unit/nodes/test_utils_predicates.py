"""Tests for :mod:`weftlyflow.nodes.utils.predicates`."""

from __future__ import annotations

import pytest

from weftlyflow.nodes.utils.predicates import evaluate_predicate


@pytest.mark.parametrize(
    ("left", "op", "right", "expected"),
    [
        (5, "equals", 5, True),
        (5, "equals", 6, False),
        (5, "not_equals", 6, True),
        (5, "greater_than", 4, True),
        (5, "greater_than_or_equal", 5, True),
        (5, "less_than", 6, True),
        (5, "less_than_or_equal", 5, True),
        ("hello", "contains", "ell", True),
        ("hello", "not_contains", "zzz", True),
        ("hello", "starts_with", "he", True),
        ("hello", "ends_with", "lo", True),
        ([], "is_empty", None, True),
        ([1], "is_not_empty", None, True),
        (None, "is_empty", None, True),
        (True, "is_true", None, True),
        (False, "is_false", None, True),
        (1, "is_true", None, True),
        (0, "is_false", None, True),
    ],
)
def test_operators(left, op, right, expected):
    assert evaluate_predicate(left, op, right) is expected


def test_unknown_operator_raises():
    with pytest.raises(ValueError):
        evaluate_predicate(1, "what", 2)  # type: ignore[arg-type]
