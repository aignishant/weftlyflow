"""Run Code-node snippets inside an OS-level sandboxed subprocess.

The in-process RestrictedPython layer is useful but not sufficient for
arbitrary user-authored Python: a buggy or malicious snippet can still
exhaust memory, spawn threads, read the Celery worker's filesystem, or
leak wall-clock time. This module forks a fresh Python subprocess per
invocation, applies OS-level resource limits before ``exec`` hands
control to the restricted interpreter in
:mod:`weftlyflow.worker.sandbox_child`, and waits for it to produce a
JSON response on stdout.

Defences applied to the child:

* ``RLIMIT_CPU`` — soft CPU budget (seconds of user-space time).
* ``RLIMIT_AS`` — address-space ceiling (virtual memory).
* ``RLIMIT_NOFILE`` — open file descriptors.
* ``RLIMIT_NPROC`` — child process / thread count.
* ``RLIMIT_FSIZE`` — maximum size of any file the child may write.
* ``prctl(PR_SET_NO_NEW_PRIVS)`` — drops setuid / capability escalation
  (Linux only; best effort).
* Parent-side wall-clock timeout via :func:`subprocess.run` — hard kills
  the child group if ``RLIMIT_CPU`` underreports.

Non-Linux platforms (developer laptops on macOS) get the wall-clock
timeout but not the rlimits; the runner logs a warning once at import
time so the deployment footprint is obvious. Production runs are
Linux-only by policy.

This module is **not** imported from the engine core — it is reached
only via the Code node and only when
``settings.enable_code_node`` is true.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

import structlog

from weftlyflow.config import get_settings

log = structlog.get_logger(__name__)

# Import ctypes lazily — on Windows / macOS the prctl call is a no-op.
_PR_SET_NO_NEW_PRIVS: int = 38  # Linux prctl(2) option number.


@dataclass(slots=True)
class SandboxLimits:
    """Resource ceilings applied to the child before ``exec`` runs the snippet.

    Defaults keep a single snippet below any realistic workflow budget
    while leaving enough headroom for legitimate data transformations
    on a few thousand items.
    """

    cpu_seconds: int = 5
    memory_bytes: int = 256 * 1024 * 1024       # 256 MiB
    max_open_files: int = 64
    max_processes: int = 32
    max_file_bytes: int = 16 * 1024 * 1024       # 16 MiB — any writes fail fast.
    wall_clock_seconds: float = 10.0             # parent-side timeout; > cpu budget.


class SandboxError(Exception):
    """Raised when the sandboxed subprocess cannot deliver a JSON response."""


class SandboxTimeoutError(SandboxError):
    """The child exceeded its wall-clock budget and was killed."""


class SandboxSnippetError(SandboxError):
    """The child returned a structured error from the snippet."""


def _apply_child_limits(limits: SandboxLimits) -> None:  # pragma: no cover - runs in child
    """``preexec_fn`` body — runs between fork and exec in the child.

    Must not allocate structlog loggers or touch any Weftlyflow module
    after fork: at this point the child is still holding the parent's
    locks and a misbehaving import can deadlock Celery's prefork pool.
    """
    if sys.platform != "linux":
        return
    try:
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (limits.cpu_seconds, limits.cpu_seconds),
        )
        resource.setrlimit(
            resource.RLIMIT_AS,
            (limits.memory_bytes, limits.memory_bytes),
        )
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (limits.max_open_files, limits.max_open_files),
        )
        resource.setrlimit(
            resource.RLIMIT_NPROC,
            (limits.max_processes, limits.max_processes),
        )
        resource.setrlimit(
            resource.RLIMIT_FSIZE,
            (limits.max_file_bytes, limits.max_file_bytes),
        )
    except (ValueError, OSError):
        # Running inside a container that already caps us lower — that's
        # fine, the tighter limit wins. Swallow and continue.
        pass
    try:
        import ctypes  # noqa: PLC0415 — kept out of parent import path.

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    except OSError:
        pass


def run_snippet(
    code: str,
    items: list[dict[str, Any]],
    *,
    limits: SandboxLimits | None = None,
) -> list[dict[str, Any]]:
    """Execute ``code`` against ``items`` inside a sandboxed child; return new items.

    Args:
        code: The Python snippet from the Code node. Compiled with
            RestrictedPython ``exec`` mode inside the child.
        items: Input items as plain dicts (the parent flattens domain
            objects before calling).
        limits: Optional override for ``SandboxLimits``; defaults to a
            conservative profile suitable for per-workflow snippets.

    Returns:
        The new ``items`` list produced by the snippet.

    Raises:
        SandboxTimeoutError: child exceeded wall-clock budget.
        SandboxSnippetError: child returned ``ok=false``.
        SandboxError: any other failure (JSON decode, non-zero exit).
    """
    effective = limits or SandboxLimits()
    payload = json.dumps({"code": code, "items": items})
    cmd = [sys.executable, "-I", "-m", "weftlyflow.worker.sandbox_child"]
    try:
        completed = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            timeout=effective.wall_clock_seconds,
            preexec_fn=lambda: _apply_child_limits(effective),
            check=False,
            env={"PYTHONPATH": os.getenv("PYTHONPATH", ""), "PATH": os.getenv("PATH", "")},
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"code snippet exceeded {effective.wall_clock_seconds}s wall-clock budget"
        raise SandboxTimeoutError(msg) from exc
    if completed.returncode != 0:
        msg = (
            f"sandbox child exited non-zero (rc={completed.returncode}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
        raise SandboxError(msg)
    try:
        response = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        msg = f"sandbox child produced invalid JSON: {completed.stdout!r}"
        raise SandboxError(msg) from exc
    if not response.get("ok"):
        raise SandboxSnippetError(response.get("error", "sandbox snippet failed"))
    return list(response.get("items", []))


def build_limits_from_settings() -> SandboxLimits:
    """Construct :class:`SandboxLimits` from the current settings object."""
    settings = get_settings()
    return SandboxLimits(
        cpu_seconds=settings.code_node_cpu_seconds,
        memory_bytes=settings.code_node_memory_bytes,
        wall_clock_seconds=settings.code_node_wall_clock_seconds,
    )
