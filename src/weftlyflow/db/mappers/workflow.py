"""Workflow mapper — bidirectional translation WorkflowEntity ↔ Workflow.

Nodes and connections are stored as JSON blobs. The translation is
deliberately defensive: missing keys fall back to defaults, unknown keys are
ignored. This lets workflow JSON written by one Weftlyflow version load in a
newer version even when fields are added.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from weftlyflow.domain.workflow import (
    Connection,
    Node,
    RetryPolicy,
    Workflow,
    WorkflowSettings,
)

if TYPE_CHECKING:
    from weftlyflow.db.entities.workflow import WorkflowEntity


def workflow_to_domain(entity: WorkflowEntity) -> Workflow:
    """Build a :class:`Workflow` from a populated :class:`WorkflowEntity` row."""
    nodes = [_node_from_json(raw) for raw in entity.nodes]
    connections = [_connection_from_json(raw) for raw in entity.connections]
    return Workflow(
        id=entity.id,
        project_id=entity.project_id,
        name=entity.name,
        nodes=nodes,
        connections=connections,
        settings=_settings_from_json(entity.settings),
        static_data=dict(entity.static_data),
        pin_data={k: list(v) for k, v in entity.pin_data.items()},
        active=entity.active,
        archived=entity.archived,
        tags=list(entity.tags),
        version_id=entity.version_id,
    )


def workflow_to_entity_kwargs(workflow: Workflow) -> dict[str, Any]:
    """Return a kwargs dict suitable for ``WorkflowEntity(**kwargs)`` or an update."""
    return {
        "id": workflow.id,
        "project_id": workflow.project_id,
        "name": workflow.name,
        "nodes": [_node_to_json(n) for n in workflow.nodes],
        "connections": [_connection_to_json(c) for c in workflow.connections],
        "settings": _settings_to_json(workflow.settings),
        "static_data": dict(workflow.static_data),
        "pin_data": {k: list(v) for k, v in workflow.pin_data.items()},
        "tags": list(workflow.tags),
        "active": workflow.active,
        "archived": workflow.archived,
        "version_id": workflow.version_id,
    }


def _node_from_json(raw: dict[str, Any]) -> Node:
    retry_raw = raw.get("retry_policy")
    retry = _retry_from_json(retry_raw) if isinstance(retry_raw, dict) else None
    return Node(
        id=str(raw["id"]),
        name=str(raw.get("name", "")),
        type=str(raw["type"]),
        type_version=int(raw.get("type_version", 1)),
        parameters=dict(raw.get("parameters", {})),
        credentials=dict(raw.get("credentials", {})),
        position=_coerce_position(raw.get("position", (0.0, 0.0))),
        disabled=bool(raw.get("disabled", False)),
        notes=raw.get("notes"),
        continue_on_fail=bool(raw.get("continue_on_fail", False)),
        retry_policy=retry,
    )


def _node_to_json(node: Node) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "type_version": node.type_version,
        "parameters": dict(node.parameters),
        "credentials": dict(node.credentials),
        "position": list(node.position),
        "disabled": node.disabled,
        "notes": node.notes,
        "continue_on_fail": node.continue_on_fail,
    }
    if node.retry_policy is not None:
        data["retry_policy"] = _retry_to_json(node.retry_policy)
    return data


def _connection_from_json(raw: dict[str, Any]) -> Connection:
    return Connection(
        source_node=str(raw["source_node"]),
        target_node=str(raw["target_node"]),
        source_port=str(raw.get("source_port", "main")),
        source_index=int(raw.get("source_index", 0)),
        target_port=str(raw.get("target_port", "main")),
        target_index=int(raw.get("target_index", 0)),
    )


def _connection_to_json(conn: Connection) -> dict[str, Any]:
    return {
        "source_node": conn.source_node,
        "target_node": conn.target_node,
        "source_port": conn.source_port,
        "source_index": conn.source_index,
        "target_port": conn.target_port,
        "target_index": conn.target_index,
    }


def _settings_from_json(raw: dict[str, Any]) -> WorkflowSettings:
    return WorkflowSettings(
        timezone=str(raw.get("timezone", "UTC")),
        timeout_seconds=int(raw.get("timeout_seconds", 3600)),
        save_manual_executions=bool(raw.get("save_manual_executions", True)),
        save_trigger_executions_on=raw.get("save_trigger_executions_on", "all"),
        error_workflow_id=raw.get("error_workflow_id"),
        caller_policy=raw.get("caller_policy", "own"),
    )


def _settings_to_json(settings: WorkflowSettings) -> dict[str, Any]:
    return {
        "timezone": settings.timezone,
        "timeout_seconds": settings.timeout_seconds,
        "save_manual_executions": settings.save_manual_executions,
        "save_trigger_executions_on": settings.save_trigger_executions_on,
        "error_workflow_id": settings.error_workflow_id,
        "caller_policy": settings.caller_policy,
    }


def _retry_from_json(raw: dict[str, Any]) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=int(raw.get("max_attempts", 1)),
        backoff_factor=float(raw.get("backoff_factor", 2.0)),
        base_delay_ms=int(raw.get("base_delay_ms", 1000)),
        max_delay_ms=int(raw.get("max_delay_ms", 60000)),
    )


def _retry_to_json(retry: RetryPolicy) -> dict[str, Any]:
    return {
        "max_attempts": retry.max_attempts,
        "backoff_factor": retry.backoff_factor,
        "base_delay_ms": retry.base_delay_ms,
        "max_delay_ms": retry.max_delay_ms,
    }


_POSITION_LEN = 2


def _coerce_position(raw: Any) -> tuple[float, float]:
    if isinstance(raw, (list, tuple)) and len(raw) >= _POSITION_LEN:
        return (float(raw[0]), float(raw[1]))
    return (0.0, 0.0)
