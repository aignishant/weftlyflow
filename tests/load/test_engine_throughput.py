"""In-process wall-clock probes on the hottest engine paths.

Budgets are deliberately loose — we catch an order-of-magnitude
regression, not a 5% one. If a run legitimately needs more time (e.g.,
CI on a weak runner), bump the budget rather than chasing a flake.

Run with::

    make test-load
"""

from __future__ import annotations

import time

import pytest

from weftlyflow.domain.execution import Item
from weftlyflow.expression import build_proxies, clear_cache, resolve

pytestmark = pytest.mark.load


_EXPR_ITERATIONS = 5_000
_EXPR_BUDGET_SECONDS = 5.0


def test_expression_eval_throughput() -> None:
    """Evaluate a small expression 5000x; must complete within 5 seconds.

    Baseline on a 2024 laptop is ~0.5s. The 10x headroom absorbs slow CI
    runners while still catching a genuine perf regression (caching
    disabled, sandbox re-spawned per call, etc).
    """
    clear_cache()
    proxies = build_proxies(
        item=Item(json={"name": "world", "n": 3}),
        inputs=[],
        workflow_id="wf",
        workflow_name="demo",
        project_id="p",
        execution_id="ex",
        execution_mode="manual",
        env_vars={},
    )
    expression = "Hello {{ $json.name }}, n is {{ $json.n * 2 }}"

    start = time.perf_counter()
    for _ in range(_EXPR_ITERATIONS):
        resolve(expression, proxies)
    elapsed = time.perf_counter() - start

    assert elapsed < _EXPR_BUDGET_SECONDS, (
        f"expression eval throughput regressed: {_EXPR_ITERATIONS} evals "
        f"took {elapsed:.2f}s (budget {_EXPR_BUDGET_SECONDS}s)"
    )
