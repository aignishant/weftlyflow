"""Smoke tests — Phase-0 gate.

These tests prove that:
    * The package imports cleanly.
    * Settings load from env without crashing.
    * The FastAPI app starts and ``/healthz`` returns 200.
    * Domain dataclasses can be constructed.

If any of these break, the bootstrap is broken — do not ship.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient


def test_package_imports() -> None:
    """``import weftlyflow`` should succeed and expose a version string."""
    import weftlyflow

    assert isinstance(weftlyflow.__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+", weftlyflow.__version__)


def test_settings_load() -> None:
    """Settings should load using test-env defaults without raising."""
    from weftlyflow.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.env == "test"
    assert settings.database_url.startswith("sqlite")


def test_healthz_ok() -> None:
    """``GET /healthz`` should return 200 with a version payload."""
    from weftlyflow.server.app import create_app

    with TestClient(create_app()) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_domain_dataclasses_construct() -> None:
    """Construct the core domain types — smoke check of field wiring."""
    from weftlyflow.domain import Connection, Node, Workflow, new_node_id, new_workflow_id

    node = Node(id=new_node_id(), name="Start", type="weftlyflow.manual_trigger")
    wf = Workflow(
        id=new_workflow_id(),
        project_id="pr_test",
        name="Smoke",
        nodes=[node],
        connections=[Connection(source_node=node.id, target_node=node.id)],
    )
    assert wf.node_by_id(node.id) is node
    assert wf.nodes[0].disabled is False


@pytest.mark.parametrize(
    "factory_name",
    ["new_workflow_id", "new_execution_id", "new_node_id"],
)
def test_id_factories_prefixed(factory_name: str) -> None:
    """ID factories must emit a prefixed ULID."""
    from weftlyflow import domain

    factory = getattr(domain, factory_name)
    value = factory()
    assert "_" in value
    assert len(value) > 20
