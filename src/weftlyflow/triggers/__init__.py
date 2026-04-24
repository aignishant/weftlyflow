"""Trigger and polling lifecycle manager.

Owns:
    constants.py : lock keys, schedule-kind tuple.
    leader.py    : Redis-backed + in-memory leader election.
    scheduler.py : APScheduler wrapper + :class:`ScheduleSpec` dataclass.
    poller.py    : generic :class:`BasePollerNode.poll` runner.
    manager.py   : :class:`ActiveTriggerManager` — activation orchestrator.

The manager runs only on the elected leader instance (see §13.3 of the bible).

See weftlyinfo.md §13.
"""

from __future__ import annotations

from weftlyflow.triggers.leader import (
    InMemoryLeaderLock,
    LeaderLock,
    RedisLeaderLock,
)
from weftlyflow.triggers.manager import (
    ActivationResult,
    ActiveTriggerManager,
    is_trigger_type,
)
from weftlyflow.triggers.scheduler import (
    APSchedulerBackend,
    InMemoryScheduler,
    Scheduler,
    ScheduleSpec,
)

__all__ = [
    "APSchedulerBackend",
    "ActivationResult",
    "ActiveTriggerManager",
    "InMemoryLeaderLock",
    "InMemoryScheduler",
    "LeaderLock",
    "RedisLeaderLock",
    "ScheduleSpec",
    "Scheduler",
    "is_trigger_type",
]
