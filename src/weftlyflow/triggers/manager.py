"""ActiveTriggerManager — top-level orchestrator for workflow activation.

Responsibilities:

* **Activate** a workflow: iterate its trigger nodes and register each with
  the right subsystem (webhook registry for :class:`WebhookTriggerNode`,
  scheduler for :class:`ScheduleTriggerNode`). Persist the resulting
  :class:`WebhookEntity` / :class:`TriggerScheduleEntity` rows so restarts
  can replay.
* **Deactivate**: undo the above.
* **Warm-up**: on boot, reload every active workflow's registrations from
  the DB into the in-memory registry + scheduler.

The manager does not talk to external services in Phase 3 — dynamic webhook
installation (e.g. Slack's ``/subscriptions``) lands with the Tier-2 nodes.

Most methods are ``async`` because they hit the async DB session. Scheduler
+ registry operations themselves are synchronous.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from weftlyflow.db.entities.trigger_schedule import TriggerScheduleEntity
from weftlyflow.db.entities.webhook import WebhookEntity
from weftlyflow.db.repositories.trigger_schedule_repo import TriggerScheduleRepository
from weftlyflow.db.repositories.webhook_repo import WebhookRepository
from weftlyflow.domain.ids import new_webhook_id
from weftlyflow.triggers.constants import SCHEDULE_KIND_INTERVAL
from weftlyflow.triggers.scheduler import ScheduleSpec
from weftlyflow.webhooks.paths import static_path
from weftlyflow.webhooks.registry import entry_from_entity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from weftlyflow.domain.workflow import Node, Workflow
    from weftlyflow.triggers.leader import LeaderLock
    from weftlyflow.triggers.scheduler import Scheduler
    from weftlyflow.webhooks.registry import WebhookRegistry
    from weftlyflow.worker.queue import ExecutionQueue

log = structlog.get_logger(__name__)

WEBHOOK_TRIGGER_TYPE = "weftlyflow.webhook_trigger"
SCHEDULE_TRIGGER_TYPE = "weftlyflow.schedule_trigger"
CHAT_TRIGGER_TYPE = "weftlyflow.trigger_chat"
_WEBHOOK_BACKED_TRIGGER_TYPES: frozenset[str] = frozenset(
    {WEBHOOK_TRIGGER_TYPE, CHAT_TRIGGER_TYPE},
)


@dataclass(slots=True)
class ActivationResult:
    """Summary returned from :meth:`ActiveTriggerManager.activate`.

    Attributes:
        webhooks_registered: Paths successfully added to the registry.
        schedules_registered: Job ids successfully added to the scheduler.
        errors: Human-readable error messages for trigger nodes that could
            not be registered. A non-empty list means the workflow is
            partially active — the caller should roll back.
    """

    webhooks_registered: list[str]
    schedules_registered: list[str]
    errors: list[str]


class ActiveTriggerManager:
    """Activate + deactivate workflows across webhook/schedule subsystems."""

    __slots__ = (
        "_leader",
        "_queue",
        "_registry",
        "_scheduler",
        "_session_factory",
    )

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[Any],
        registry: WebhookRegistry,
        scheduler: Scheduler,
        queue: ExecutionQueue,
        leader: LeaderLock,
    ) -> None:
        """Wire the subsystems the manager coordinates."""
        self._session_factory = session_factory
        self._registry = registry
        self._scheduler = scheduler
        self._queue = queue
        self._leader = leader

    async def activate(self, workflow: Workflow) -> ActivationResult:
        """Register every trigger node in ``workflow`` with the right subsystem."""
        result = ActivationResult([], [], [])
        async with self._session_factory() as session:
            for node in workflow.nodes:
                if node.disabled:
                    continue
                try:
                    if node.type in _WEBHOOK_BACKED_TRIGGER_TYPES:
                        path = await self._register_webhook(session, workflow, node)
                        result.webhooks_registered.append(path)
                    elif node.type == SCHEDULE_TRIGGER_TYPE:
                        job_id = await self._register_schedule(session, workflow, node)
                        result.schedules_registered.append(job_id)
                except Exception as exc:
                    result.errors.append(f"{node.id}: {exc}")
                    log.warning(
                        "trigger_activation_failed",
                        workflow_id=workflow.id,
                        node_id=node.id,
                        node_type=node.type,
                        error=str(exc),
                    )
            await session.commit()
        return result

    async def deactivate(self, workflow: Workflow) -> None:
        """Tear down every registration owned by ``workflow``."""
        async with self._session_factory() as session:
            wh_rows = await WebhookRepository(session).list_for_workflow(workflow.id)
            for wh in wh_rows:
                self._registry.unregister(wh.path, wh.method)
            await WebhookRepository(session).delete_for_workflow(workflow.id)

            sched_rows = await TriggerScheduleRepository(session).list_for_workflow(workflow.id)
            for sched in sched_rows:
                self._scheduler.remove_job(_schedule_job_id(sched.workflow_id, sched.node_id))
            await TriggerScheduleRepository(session).delete_for_workflow(workflow.id)
            await session.commit()

    async def warm_up(self) -> int:
        """Reload every persisted webhook + schedule into the in-memory state.

        Returns the number of registrations re-hydrated.
        """
        async with self._session_factory() as session:
            webhooks = await WebhookRepository(session).list_all()
            self._registry.load(entry_from_entity(row) for row in webhooks)

            schedule_rows = await TriggerScheduleRepository(session).list_all()
            for row in schedule_rows:
                spec = _schedule_spec_from_row(row)
                job_id = _schedule_job_id(row.workflow_id, row.node_id)
                self._scheduler.add_job(
                    job_id=job_id,
                    spec=spec,
                    callback=self._build_schedule_callback(row),
                )
            return len(webhooks) + len(schedule_rows)

    async def _register_webhook(
        self, session: AsyncSession, workflow: Workflow, node: Node,
    ) -> str:
        params = node.parameters or {}
        path = static_path(workflow.id, node.id, params.get("path"))
        method = str(params.get("method", "POST")).upper()
        response_mode = str(params.get("response_mode", "immediately"))

        entity = WebhookEntity(
            id=new_webhook_id(),
            workflow_id=workflow.id,
            project_id=workflow.project_id,
            node_id=node.id,
            path=path,
            method=method,
            is_dynamic=False,
            response_mode=response_mode,
        )
        await WebhookRepository(session).create(entity)
        self._registry.register(entry_from_entity(entity))
        log.info(
            "webhook_registered",
            workflow_id=workflow.id,
            node_id=node.id,
            method=method,
            path=path,
        )
        return path

    async def _register_schedule(
        self, session: AsyncSession, workflow: Workflow, node: Node,
    ) -> str:
        params = node.parameters or {}
        spec = _schedule_spec_from_params(params)
        spec.validate()
        kind = spec.kind

        entity = TriggerScheduleEntity(
            id=f"ts_{new_webhook_id()[3:]}",
            workflow_id=workflow.id,
            project_id=workflow.project_id,
            node_id=node.id,
            kind=kind,
            cron_expression=spec.cron_expression,
            interval_seconds=spec.interval_seconds,
            timezone=spec.timezone,
        )
        await TriggerScheduleRepository(session).create(entity)

        job_id = _schedule_job_id(workflow.id, node.id)
        self._scheduler.add_job(
            job_id=job_id,
            spec=spec,
            callback=self._build_schedule_callback(entity),
        )
        log.info(
            "schedule_registered",
            workflow_id=workflow.id,
            node_id=node.id,
            kind=kind,
        )
        return job_id

    def _build_schedule_callback(self, row: TriggerScheduleEntity) -> Any:
        """Return a zero-arg callable the scheduler can invoke each tick."""
        import asyncio  # noqa: PLC0415

        from weftlyflow.domain.ids import new_execution_id  # noqa: PLC0415
        from weftlyflow.worker.queue import ExecutionRequest  # noqa: PLC0415

        queue = self._queue
        leader = self._leader
        workflow_id = row.workflow_id
        project_id = row.project_id
        node_id = row.node_id

        def _fire() -> None:
            if not leader.is_leader():
                return
            request = ExecutionRequest(
                execution_id=new_execution_id(),
                workflow_id=workflow_id,
                project_id=project_id,
                mode="trigger",
                triggered_by=f"schedule:{node_id}",
                initial_items=[{"node_id": node_id}],
            )
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop is None:
                # APScheduler's BackgroundScheduler runs us in a dedicated
                # thread with no loop; spin up a short-lived one.
                asyncio.run(queue.enqueue(request))
            else:
                # Scheduler runs inside an active loop (inline tests) — hand
                # off without blocking.
                _schedule_on_loop(running_loop, queue.enqueue(request))

        return _fire


def _schedule_job_id(workflow_id: str, node_id: str) -> str:
    return f"schedule:{workflow_id}:{node_id}"


def _schedule_spec_from_params(params: dict[str, Any]) -> ScheduleSpec:
    kind = str(params.get("kind", SCHEDULE_KIND_INTERVAL))
    return ScheduleSpec(
        kind=kind,
        cron_expression=_optional_str(params.get("cron_expression")),
        interval_seconds=_optional_int(params.get("interval_seconds")),
        timezone=str(params.get("timezone", "UTC")),
    )


def _schedule_spec_from_row(row: TriggerScheduleEntity) -> ScheduleSpec:
    return ScheduleSpec(
        kind=row.kind,
        cron_expression=row.cron_expression,
        interval_seconds=row.interval_seconds,
        timezone=row.timezone,
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        msg = f"interval_seconds must be an integer, got {value!r}"
        raise ValueError(msg) from exc


def is_trigger_type(node_type: str) -> bool:
    """Return True when ``node_type`` is managed by the activation flow."""
    return node_type in _WEBHOOK_BACKED_TRIGGER_TYPES or node_type == SCHEDULE_TRIGGER_TYPE


def _schedule_on_loop(loop: Any, coro: Any) -> None:
    """Spawn ``coro`` on ``loop`` and keep a reference so the task survives GC."""
    task = loop.create_task(coro)
    _loop_tasks.add(task)
    task.add_done_callback(_loop_tasks.discard)


_loop_tasks: set[Any] = set()
