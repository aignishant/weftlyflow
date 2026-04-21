"""Execution mapper — translate between Execution domain and (Execution, ExecutionData) rows.

Two sides:

* ``execution_to_domain(entity, data)`` reassembles a domain :class:`Execution`
  from the metadata row + the run-data sidecar.
* ``execution_to_entity_kwargs(execution)`` / ``execution_to_data_payload(execution)``
  split a domain execution back into the two rows the database expects.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from weftlyflow.db.mappers.workflow import (
    _connection_from_json,
    _node_from_json,
    _settings_from_json,
    workflow_to_domain,
    workflow_to_entity_kwargs,
)
from weftlyflow.domain.execution import (
    Execution,
    ExecutionMode,
    ExecutionStatus,
    Item,
    NodeError,
    NodeRunData,
    RunData,
)
from weftlyflow.domain.workflow import Workflow

if TYPE_CHECKING:
    from weftlyflow.db.entities.execution import ExecutionEntity
    from weftlyflow.db.entities.execution_data import ExecutionDataEntity

_NodeStatus = Literal["success", "error", "disabled"]


def execution_to_domain(
    entity: ExecutionEntity,
    data: ExecutionDataEntity,
) -> Execution:
    """Reassemble an :class:`Execution` from metadata + data rows."""
    snapshot = _workflow_from_snapshot(data.workflow_snapshot)
    return Execution(
        id=entity.id,
        workflow_id=entity.workflow_id,
        workflow_snapshot=snapshot,
        mode=cast(ExecutionMode, entity.mode),
        status=cast(ExecutionStatus, entity.status),
        started_at=entity.started_at,
        finished_at=entity.finished_at,
        wait_till=entity.wait_till,
        run_data=_run_data_from_json(data.run_data),
        data_storage="db",
        triggered_by=entity.triggered_by,
    )


def execution_to_entity_kwargs(execution: Execution, *, project_id: str) -> dict[str, Any]:
    """Return kwargs for ``ExecutionEntity(**kwargs)`` — metadata only."""
    return {
        "id": execution.id,
        "workflow_id": execution.workflow_id,
        "project_id": project_id,
        "mode": execution.mode,
        "status": execution.status,
        "started_at": execution.started_at,
        "finished_at": execution.finished_at,
        "wait_till": execution.wait_till,
        "triggered_by": execution.triggered_by,
    }


def execution_to_data_payload(execution: Execution) -> dict[str, Any]:
    """Return kwargs for ``ExecutionDataEntity(**kwargs)`` — the bulky side."""
    return {
        "execution_id": execution.id,
        "workflow_snapshot": _workflow_to_snapshot(execution.workflow_snapshot),
        "run_data": _run_data_to_json(execution.run_data),
        "storage_kind": "db",
    }


def _workflow_from_snapshot(raw: dict[str, Any]) -> Workflow:
    nodes = [_node_from_json(n) for n in raw.get("nodes", [])]
    connections = [_connection_from_json(c) for c in raw.get("connections", [])]
    return Workflow(
        id=str(raw["id"]),
        project_id=str(raw.get("project_id", "")),
        name=str(raw.get("name", "")),
        nodes=nodes,
        connections=connections,
        settings=_settings_from_json(raw.get("settings", {})),
        static_data=dict(raw.get("static_data", {})),
        pin_data={k: list(v) for k, v in raw.get("pin_data", {}).items()},
        active=bool(raw.get("active", False)),
        archived=bool(raw.get("archived", False)),
        tags=list(raw.get("tags", [])),
        version_id=raw.get("version_id"),
    )


def _workflow_to_snapshot(workflow: Workflow) -> dict[str, Any]:
    kwargs = workflow_to_entity_kwargs(workflow)
    # Convert the kwargs shape (which already JSON-safe) to the snapshot shape.
    return dict(kwargs)


def _run_data_from_json(raw: dict[str, Any]) -> RunData:
    per_node_raw = raw.get("per_node", {})
    per_node: dict[str, list[NodeRunData]] = {
        node_id: [_node_run_data_from_json(r) for r in runs]
        for node_id, runs in per_node_raw.items()
    }
    return RunData(per_node=per_node)


def _run_data_to_json(run_data: RunData) -> dict[str, Any]:
    return {
        "per_node": {
            node_id: [_node_run_data_to_json(r) for r in runs]
            for node_id, runs in run_data.per_node.items()
        },
    }


def _node_run_data_from_json(raw: dict[str, Any]) -> NodeRunData:
    items_raw = raw.get("items", [])
    items: list[list[Item]] = [
        [_item_from_json(i) for i in port] for port in items_raw
    ]
    error_raw = raw.get("error")
    error = _error_from_json(error_raw) if isinstance(error_raw, dict) else None
    started = raw.get("started_at")
    started_dt = (
        datetime.fromisoformat(started) if isinstance(started, str) else cast(datetime, started)
    )
    return NodeRunData(
        items=items,
        execution_time_ms=int(raw.get("execution_time_ms", 0)),
        started_at=started_dt,
        status=cast("_NodeStatus", raw.get("status", "success")),
        error=error,
    )


def _node_run_data_to_json(nrd: NodeRunData) -> dict[str, Any]:
    return {
        "items": [[_item_to_json(i) for i in port] for port in nrd.items],
        "execution_time_ms": nrd.execution_time_ms,
        "started_at": nrd.started_at.isoformat(),
        "status": nrd.status,
        "error": _error_to_json(nrd.error) if nrd.error is not None else None,
    }


def _item_from_json(raw: dict[str, Any]) -> Item:
    error_raw = raw.get("error")
    error = _error_from_json(error_raw) if isinstance(error_raw, dict) else None
    return Item(
        json=dict(raw.get("json", {})),
        binary={},  # binary offload is Phase 8
        paired_item=[],  # provenance links are Phase 8
        error=error,
    )


def _item_to_json(item: Item) -> dict[str, Any]:
    return {
        "json": dict(item.json),
        "error": _error_to_json(item.error) if item.error is not None else None,
    }


def _error_from_json(raw: dict[str, Any]) -> NodeError:
    return NodeError(
        message=str(raw.get("message", "")),
        description=raw.get("description"),
        code=raw.get("code"),
    )


def _error_to_json(error: NodeError) -> dict[str, Any]:
    return {
        "message": error.message,
        "description": error.description,
        "code": error.code,
    }


# Silence unused-import warnings — these helpers re-expose workflow-mapper
# internals for tests while preserving encapsulation.
__all__ = [
    "execution_to_data_payload",
    "execution_to_domain",
    "execution_to_entity_kwargs",
    "workflow_to_domain",
]
