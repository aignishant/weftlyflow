"""Celery worker entry point + task definitions.

Public surface:

* :class:`ExecutionRequest` — payload shape accepted by every queue impl.
* :class:`ExecutionQueue` — protocol implemented by both the Celery-backed
  and the inline test queue.
* :class:`CeleryExecutionQueue` / :class:`InlineExecutionQueue` — concrete
  implementations. The FastAPI app picks one at boot based on settings.

See weftlyinfo.md §14 and `memory/cheatsheet_celery.md`.
"""

from __future__ import annotations

from weftlyflow.worker.queue import (
    CeleryExecutionQueue,
    ExecutionQueue,
    ExecutionRequest,
    InlineExecutionQueue,
)

__all__ = [
    "CeleryExecutionQueue",
    "ExecutionQueue",
    "ExecutionRequest",
    "InlineExecutionQueue",
]
