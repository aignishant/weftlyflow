"""Unit tests for :mod:`weftlyflow.expression.tokenizer`."""

from __future__ import annotations

import pytest

from weftlyflow.expression.errors import ExpressionSyntaxError
from weftlyflow.expression.tokenizer import (
    ExpressionChunk,
    LiteralChunk,
    contains_expression,
    is_single_expression,
    tokenize,
)


def test_tokenize_empty_returns_empty_list() -> None:
    assert tokenize("") == []


def test_tokenize_pure_literal() -> None:
    chunks = tokenize("hello world")
    assert chunks == [LiteralChunk("hello world")]


def test_tokenize_single_expression() -> None:
    chunks = tokenize("{{ $json.x }}")
    assert len(chunks) == 1
    chunk = chunks[0]
    assert isinstance(chunk, ExpressionChunk)
    assert chunk.source == "$json.x"
    assert chunk.offset == 0


def test_tokenize_mixed_template() -> None:
    chunks = tokenize("hello {{ $json.name }} world")
    assert [type(c).__name__ for c in chunks] == [
        "LiteralChunk", "ExpressionChunk", "LiteralChunk",
    ]
    assert chunks[0] == LiteralChunk("hello ")
    assert isinstance(chunks[1], ExpressionChunk)
    assert chunks[1].source == "$json.name"
    assert chunks[2] == LiteralChunk(" world")


def test_tokenize_back_to_back_expressions() -> None:
    chunks = tokenize("{{ a }}{{ b }}")
    assert [c.source if isinstance(c, ExpressionChunk) else None for c in chunks] == ["a", "b"]


def test_tokenize_unterminated_raises() -> None:
    with pytest.raises(ExpressionSyntaxError):
        tokenize("hello {{ $json.x")


def test_tokenize_empty_expression_raises() -> None:
    with pytest.raises(ExpressionSyntaxError):
        tokenize("{{   }}")


def test_is_single_expression_true_only_for_one_expr_chunk() -> None:
    assert is_single_expression(tokenize("{{ 1 }}")) is True
    assert is_single_expression(tokenize("x {{ 1 }}")) is False
    assert is_single_expression(tokenize("literal")) is False
    assert is_single_expression([]) is False


def test_contains_expression() -> None:
    assert contains_expression("{{ x }}") is True
    assert contains_expression("{not an expr}") is False
    assert contains_expression("") is False
