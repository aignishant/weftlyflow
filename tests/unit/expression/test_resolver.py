"""End-to-end tests for :mod:`weftlyflow.expression.resolver`."""

from __future__ import annotations

from typing import Any

import pytest

from weftlyflow.domain.execution import Item
from weftlyflow.expression import build_proxies, clear_cache, filter_env, resolve, resolve_tree
from weftlyflow.expression.errors import (
    ExpressionEvalError,
    ExpressionSecurityError,
    ExpressionSyntaxError,
)


def _proxies(**overrides: Any) -> dict[str, Any]:
    clear_cache()
    defaults: dict[str, Any] = {
        "item": Item(json={"name": "world", "n": 3, "nested": {"a": 1}}),
        "inputs": [Item(json={"name": "world"}), Item(json={"name": "mars"})],
        "workflow_id": "wf_1",
        "workflow_name": "demo",
        "project_id": "pr_1",
        "execution_id": "ex_1",
        "execution_mode": "manual",
        "env_vars": {"KEY": "v"},
    }
    defaults.update(overrides)
    return build_proxies(**defaults)


def test_single_expression_returns_raw_type() -> None:
    assert resolve("{{ $json.name }}", _proxies()) == "world"
    assert resolve("{{ $json.n }}", _proxies()) == 3
    assert resolve("{{ [1, 2, 3] }}", _proxies()) == [1, 2, 3]


def test_mixed_template_returns_string_concat() -> None:
    out = resolve("Hi {{ $json.name }}! n={{ $json.n }}", _proxies())
    assert out == "Hi world! n=3"


def test_no_expression_passes_through() -> None:
    assert resolve("plain text", _proxies()) == "plain text"
    assert resolve(42, _proxies()) == 42
    assert resolve(None, _proxies()) is None


def test_dot_access_on_dicts() -> None:
    assert resolve("{{ $json.nested.a }}", _proxies()) == 1


def test_list_comprehension_with_builtins() -> None:
    assert resolve("{{ [i * 2 for i in range($json.n)] }}", _proxies()) == [0, 2, 4]


def test_input_proxy_methods() -> None:
    assert resolve("{{ $input.count() }}", _proxies()) == 2
    assert resolve("{{ $input.first().name }}", _proxies()) == "world"
    assert resolve("{{ $input.last().name }}", _proxies()) == "mars"


def test_env_is_filtered_to_whitelisted_prefix() -> None:
    raw = {
        "WEFTLYFLOW_VAR_FOO": "yes",
        "DATABASE_URL": "secret-should-be-hidden",
    }
    filtered = filter_env(raw)
    assert filtered == {"FOO": "yes"}


def test_rejects_import() -> None:
    with pytest.raises(ExpressionSecurityError):
        resolve("{{ __import__('os') }}", _proxies())


def test_rejects_dunder_attribute_access() -> None:
    with pytest.raises(ExpressionSecurityError):
        resolve("{{ (1).__class__ }}", _proxies())


def test_reports_runtime_error_as_expression_eval() -> None:
    with pytest.raises(ExpressionEvalError):
        resolve("{{ $json.missing_key_raises }}", _proxies())


def test_unterminated_raises_syntax_error() -> None:
    with pytest.raises(ExpressionSyntaxError):
        resolve("{{ missing close", _proxies())


def test_resolve_tree_walks_nested_structures() -> None:
    tree = {
        "url": "https://api.example.com/{{ $json.name }}",
        "headers": {"X-N": "{{ $json.n }}"},
        "items": [{"id": "{{ $json.n }}"}],
    }
    out = resolve_tree(tree, _proxies())
    # Single-expression leaves preserve the raw type; mixed templates stringify.
    assert out == {
        "url": "https://api.example.com/world",
        "headers": {"X-N": 3},
        "items": [{"id": 3}],
    }


def test_resolve_tree_preserves_non_string_types() -> None:
    tree = {"a": 1, "b": True, "c": None, "d": [1, 2]}
    out = resolve_tree(tree, _proxies())
    assert out == {"a": 1, "b": True, "c": None, "d": [1, 2]}


def test_builtins_available() -> None:
    assert resolve("{{ len($input.all()) }}", _proxies()) == 2
    assert resolve("{{ sorted([3, 1, 2]) }}", _proxies()) == [1, 2, 3]
    assert resolve("{{ sum([1, 2, 3]) }}", _proxies()) == 6


def test_workflow_and_execution_proxies() -> None:
    assert resolve("{{ $workflow.name }}", _proxies()) == "demo"
    assert resolve("{{ $execution.id }}", _proxies()) == "ex_1"
    assert resolve("{{ $execution.mode }}", _proxies()) == "manual"


def test_now_and_today_produce_strings() -> None:
    assert isinstance(resolve("{{ $now.to_iso() }}", _proxies()), str)
    assert isinstance(resolve("{{ $today.to_iso() }}", _proxies()), str)


def test_expression_cache_returns_consistent_result() -> None:
    # Run the same expression twice to exercise the lru_cache path.
    proxies = _proxies()
    assert resolve("{{ $json.n + 1 }}", proxies) == 4
    assert resolve("{{ $json.n + 1 }}", proxies) == 4
