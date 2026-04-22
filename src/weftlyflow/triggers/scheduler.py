"""APScheduler wrapper — the Weftlyflow-shaped surface over the library.

We wrap APScheduler for three reasons:

1. Our callers want to speak in Weftlyflow terms (workflow_id, node_id,
   cron/interval) rather than APScheduler triggers.
2. The unit tests want to inject a fake scheduler without needing the full
   third-party dependency.
3. We centralise the translation between our stored
   :class:`TriggerScheduleEntity` rows and APScheduler's trigger arguments.

Production uses :class:`APSchedulerBackend`; tests use
:class:`InMemoryScheduler`, which records jobs in a dict and fires them
synchronously via :meth:`fire_now`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from weftlyflow.triggers.constants import (
    SCHEDULE_KIND_CRON,
    SCHEDULE_KIND_INTERVAL,
    SCHEDULE_KINDS,
)

log = structlog.get_logger(__name__)


@dataclass(slots=True, frozen=True)
class ScheduleSpec:
    """Pure description of a schedule — no APScheduler types.

    Attributes:
        kind: ``"cron"`` or ``"interval"``.
        cron_expression: Required when ``kind == "cron"``. Five-field cron.
        interval_seconds: Required when ``kind == "interval"``.
        timezone: IANA TZ name. Defaults to ``UTC``.
    """

    kind: str
    cron_expression: str | None = None
    interval_seconds: int | None = None
    timezone: str = "UTC"

    def validate(self) -> None:
        """Raise :class:`ValueError` if the spec is internally inconsistent."""
        if self.kind not in SCHEDULE_KINDS:
            msg = f"unknown schedule kind {self.kind!r}"
            raise ValueError(msg)
        if self.kind == SCHEDULE_KIND_CRON and not self.cron_expression:
            msg = "cron schedule requires a cron_expression"
            raise ValueError(msg)
        if self.kind == SCHEDULE_KIND_INTERVAL and not self.interval_seconds:
            msg = "interval schedule requires interval_seconds"
            raise ValueError(msg)


class Scheduler(Protocol):
    """Minimal contract every scheduler backend implements."""

    def add_job(
        self,
        *,
        job_id: str,
        spec: ScheduleSpec,
        callback: Any,
        args: tuple[Any, ...] = (),
    ) -> None:
        """Register ``callback`` under ``job_id`` with the given schedule."""

    def remove_job(self, job_id: str) -> None:
        """Drop the job if present. Silent no-op if missing."""

    def start(self) -> None:
        """Begin dispatching jobs on their schedule."""

    def shutdown(self) -> None:
        """Stop dispatching jobs; releases the background thread."""

    def has_job(self, job_id: str) -> bool:
        """Return True if a job is registered under ``job_id``."""


class InMemoryScheduler:
    """Scheduler stub usable from unit tests.

    Jobs are stored in a dict and can be triggered synchronously with
    :meth:`fire_now` — the wall-clock schedule is ignored. Tests validate
    that the manager adds/removes jobs under the expected ids.
    """

    __slots__ = ("_jobs", "started")

    def __init__(self) -> None:
        """Initialise with an empty job table."""
        self._jobs: dict[str, tuple[Any, tuple[Any, ...]]] = {}
        self.started = False

    def add_job(
        self,
        *,
        job_id: str,
        spec: ScheduleSpec,
        callback: Any,
        args: tuple[Any, ...] = (),
    ) -> None:
        """Store the job under ``job_id``."""
        spec.validate()
        self._jobs[job_id] = (callback, args)

    def remove_job(self, job_id: str) -> None:
        """Remove ``job_id`` if present."""
        self._jobs.pop(job_id, None)

    def start(self) -> None:
        """Mark the scheduler as started — jobs still fire via :meth:`fire_now`."""
        self.started = True

    def shutdown(self) -> None:
        """Mark the scheduler as stopped."""
        self.started = False

    def has_job(self, job_id: str) -> bool:
        """Return True if ``job_id`` is registered."""
        return job_id in self._jobs

    def fire_now(self, job_id: str) -> Any:
        """Invoke the registered callback synchronously and return its result."""
        callback, args = self._jobs[job_id]
        return callback(*args)


class APSchedulerBackend:
    """Production scheduler — defers to APScheduler's :class:`BackgroundScheduler`.

    Constructed lazily so importing the trigger package doesn't require the
    third-party dependency to be installed in contexts where it isn't used
    (e.g. the test suite which uses :class:`InMemoryScheduler`).
    """

    __slots__ = ("_scheduler",)

    def __init__(self) -> None:
        """Create but don't start the underlying :class:`BackgroundScheduler`."""
        from apscheduler.schedulers.background import BackgroundScheduler  # noqa: PLC0415

        self._scheduler = BackgroundScheduler(timezone="UTC")

    def add_job(
        self,
        *,
        job_id: str,
        spec: ScheduleSpec,
        callback: Any,
        args: tuple[Any, ...] = (),
    ) -> None:
        """Translate the spec into APScheduler's trigger and register."""
        from apscheduler.triggers.cron import CronTrigger  # noqa: PLC0415
        from apscheduler.triggers.interval import IntervalTrigger  # noqa: PLC0415

        spec.validate()
        if spec.kind == SCHEDULE_KIND_CRON:
            assert spec.cron_expression is not None
            trigger = CronTrigger.from_crontab(spec.cron_expression, timezone=spec.timezone)
        else:
            assert spec.interval_seconds is not None
            trigger = IntervalTrigger(seconds=spec.interval_seconds, timezone=spec.timezone)
        self._scheduler.add_job(callback, trigger=trigger, id=job_id, args=list(args))

    def remove_job(self, job_id: str) -> None:
        """Drop ``job_id``; ignored if missing."""
        import contextlib  # noqa: PLC0415 — keep stdlib import local to the catch.

        with contextlib.suppress(Exception):
            self._scheduler.remove_job(job_id)

    def start(self) -> None:
        """Launch the APScheduler background thread."""
        self._scheduler.start()

    def shutdown(self) -> None:
        """Shut down APScheduler cleanly."""
        self._scheduler.shutdown(wait=False)

    def has_job(self, job_id: str) -> bool:
        """Return True if ``job_id`` is currently registered."""
        return self._scheduler.get_job(job_id) is not None
