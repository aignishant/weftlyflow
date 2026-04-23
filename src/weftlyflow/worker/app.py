"""Celery application instance.

Phase-0 skeleton — broker/backend from settings, no tasks yet. The ``include=``
list grows in Phase 3 as we add ``weftlyflow.worker.tasks``.

Invocation::

    celery -A weftlyflow.worker.app worker -l info -Q executions,polling,io,priority
    celery -A weftlyflow.worker.app beat -l info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from weftlyflow.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "weftlyflow",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["weftlyflow.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_hijack_root_logger=False,
    task_soft_time_limit=_settings.worker_task_soft_time_limit_seconds,
    task_time_limit=_settings.worker_task_time_limit_seconds,
    task_default_queue="executions",
    task_routes={
        "weftlyflow.execute_workflow": {"queue": "executions"},
        "weftlyflow.prune_audit_events": {"queue": "io"},
    },
    beat_schedule={
        "prune-audit-events-daily": {
            "task": "weftlyflow.prune_audit_events",
            # 03:17 UTC — odd minute avoids the top-of-hour rush most
            # third-party cron setups land on.
            "schedule": crontab(hour="3", minute="17"),
        },
    },
)
