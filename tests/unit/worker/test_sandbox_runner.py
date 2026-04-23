"""End-to-end tests for the Code-node subprocess sandbox.

These tests spawn real child processes (they are fast — the sandbox
startup cost is ~100ms on Linux). Marker ``sandbox`` keeps them easy
to skip on constrained runners.
"""

from __future__ import annotations

import sys

import pytest

from weftlyflow.worker.sandbox_runner import (
    SandboxError,
    SandboxLimits,
    SandboxSnippetError,
    SandboxTimeoutError,
    run_snippet,
)

pytestmark = pytest.mark.sandbox


def test_identity_snippet_returns_items_unchanged() -> None:
    """An empty-body snippet binds ``items`` unchanged."""
    out = run_snippet("pass", [{"v": 1}, {"v": 2}])
    assert out == [{"v": 1}, {"v": 2}]


def test_snippet_can_mutate_items_list() -> None:
    """The published contract: write to ``items`` to produce output."""
    code = "items = [{'doubled': row['v'] * 2} for row in items]"
    assert run_snippet(code, [{"v": 3}, {"v": 5}]) == [{"doubled": 6}, {"doubled": 10}]


def test_snippet_cannot_import_modules() -> None:
    """``__import__`` is not in the child's builtins."""
    with pytest.raises(SandboxSnippetError):
        run_snippet("import os\nitems = []", [])


def test_snippet_cannot_open_files() -> None:
    """``open`` is stripped from the child's builtins."""
    with pytest.raises(SandboxSnippetError):
        run_snippet("open('/etc/passwd')\nitems=[]", [])


def test_snippet_cannot_reach_globals_via_format() -> None:
    """The str.format bypass that worked before 8a must stay closed.

    RestrictedPython's compile step rejects dunder attribute access at
    parse time in the child, so this dies during compile — but the
    assertion is that it *never* succeeds.
    """
    code = 'x = "{0.__globals__}".format(lambda: 1)\nitems = [{"x": x}]'
    with pytest.raises(SandboxSnippetError):
        run_snippet(code, [])


def test_snippet_times_out() -> None:
    """A wall-clock-bound snippet is killed by the parent's timeout."""
    limits = SandboxLimits(cpu_seconds=1, wall_clock_seconds=0.5)
    code = "while True:\n    items = items"
    with pytest.raises((SandboxTimeoutError, SandboxError)):
        run_snippet(code, [], limits=limits)


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS only enforced on Linux")
def test_snippet_memory_limit_triggers_failure() -> None:
    """Excessive memory allocation trips ``RLIMIT_AS``."""
    limits = SandboxLimits(memory_bytes=32 * 1024 * 1024, wall_clock_seconds=5.0)
    # Allocate ~256 MiB of string memory — should exceed the 32 MiB cap.
    code = "blob = 'x' * (256 * 1024 * 1024)\nitems = [{'len': len(blob)}]"
    with pytest.raises((SandboxSnippetError, SandboxError)):
        run_snippet(code, [], limits=limits)


def test_syntax_error_surfaces_as_snippet_error() -> None:
    with pytest.raises(SandboxSnippetError):
        run_snippet("def broken(:\n    pass", [])


def test_snippet_must_leave_items_as_list() -> None:
    with pytest.raises(SandboxSnippetError):
        run_snippet("items = 42", [])
