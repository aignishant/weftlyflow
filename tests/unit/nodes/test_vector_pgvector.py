"""Unit tests for :class:`VectorPgvectorNode`.

No live Postgres: the ``_open_connection`` hook is monkey-patched with
a fake async connection so we can assert on the SQL that would be
issued and the shape of the emitted item.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PostgresDsnCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai import vector_pgvector as pkg
from weftlyflow.nodes.ai.vector_pgvector import VectorPgvectorNode
from weftlyflow.nodes.ai.vector_pgvector import node as node_module

_CRED_ID: str = "cr_pg"
_PROJECT_ID: str = "pr_test"
_DSN: str = "postgresql://u:p@localhost:5432/db"


class _FakeCursor:
    """Records every ``execute`` call, returns canned ``fetchall`` rows."""

    def __init__(
        self,
        owner: _FakeConnection,
        *,
        fetch: list[tuple[Any, ...]],
        rowcount: int,
    ) -> None:
        self._owner = owner
        self._fetch = fetch
        self.rowcount = rowcount

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def execute(
        self, stmt: str, params: tuple[Any, ...] = (),
    ) -> None:
        self._owner.calls.append((stmt, params))

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._fetch)


class _FakeConnection:
    """Minimal psycopg.AsyncConnection stand-in for unit tests."""

    def __init__(
        self,
        *,
        fetch_queue: list[list[tuple[Any, ...]]] | None = None,
        rowcount_queue: list[int] | None = None,
    ) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._fetch_queue: list[list[tuple[Any, ...]]] = list(
            fetch_queue or [],
        )
        self._rowcount_queue: list[int] = list(rowcount_queue or [])

    def cursor(self) -> _FakeCursor:
        fetch = self._fetch_queue.pop(0) if self._fetch_queue else []
        rowcount = self._rowcount_queue.pop(0) if self._rowcount_queue else 0
        return _FakeCursor(self, fetch=fetch, rowcount=rowcount)

    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


def _resolver(dsn: str = _DSN) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.postgres_dsn": PostgresDsnCredential},
        rows={_CRED_ID: ("weftlyflow.postgres_dsn", {"dsn": dsn}, _PROJECT_ID)},
    )


def _node(**parameters: object) -> Node:
    return Node(
        id="node_1",
        name="PgVec",
        type="weftlyflow.vector_pgvector",
        parameters=dict(parameters),
        credentials={"postgres_dsn": _CRED_ID},
    )


def _ctx_for(
    node: Node,
    *,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=resolver or _resolver(),
    )


def _install_fake(
    monkeypatch: pytest.MonkeyPatch,
    conn: _FakeConnection,
) -> list[str]:
    dsns: list[str] = []

    async def fake_open(dsn: str) -> _FakeConnection:
        dsns.append(dsn)
        return conn

    monkeypatch.setattr(node_module, "_open_connection", fake_open)
    return dsns


# --- package surface -------------------------------------------------


def test_package_exposes_node_attribute() -> None:
    assert pkg.NODE is VectorPgvectorNode


# --- connection + credential plumbing --------------------------------


async def test_missing_credential_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(operation="clear")
    ctx = ExecutionContext(
        workflow=build_workflow([node], [], project_id=_PROJECT_ID),
        execution_id="ex",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=None,
    )
    with pytest.raises(NodeExecutionError, match="postgres_dsn credential"):
        await VectorPgvectorNode().execute(ctx, [Item()])


async def test_empty_dsn_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(operation="clear")
    with pytest.raises(NodeExecutionError, match="empty 'dsn'"):
        await VectorPgvectorNode().execute(
            _ctx_for(node, resolver=_resolver(dsn="")), [Item()],
        )


async def test_connect_failure_is_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_open(_: str) -> _FakeConnection:
        raise psycopg.OperationalError("boom")

    monkeypatch.setattr(node_module, "_open_connection", fail_open)
    node = _node(operation="clear")
    with pytest.raises(NodeExecutionError, match="connection failed"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])


async def test_uses_dsn_from_credential_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection(rowcount_queue=[0])
    dsns = _install_fake(monkeypatch, conn)
    node = _node(operation="clear", namespace="ns")
    await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
    assert dsns == [_DSN]


# --- ensure_schema ---------------------------------------------------


async def test_ensure_schema_emits_three_idempotent_statements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection()
    _install_fake(monkeypatch, conn)
    node = _node(operation="ensure_schema", table="vecs", dimensions=16)
    out = await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
    assert len(conn.calls) == 3
    assert "CREATE EXTENSION IF NOT EXISTS vector" in conn.calls[0][0]
    assert "vector(16)" in conn.calls[1][0]
    assert "CREATE INDEX IF NOT EXISTS vecs_namespace_idx" in conn.calls[2][0]
    assert out[0][0].json == {
        "operation": "ensure_schema", "table": "vecs", "dimensions": 16,
    }


async def test_ensure_schema_rejects_bad_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(
        operation="ensure_schema", table="bad table", dimensions=4,
    )
    with pytest.raises(NodeExecutionError, match="'table'"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])


# --- upsert ----------------------------------------------------------


async def test_upsert_issues_insert_with_json_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection()
    _install_fake(monkeypatch, conn)
    node = _node(
        operation="upsert", namespace="ns", id="r1",
        vector=[1.0, 0.0], payload={"doc": "a"},
    )
    out = await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
    stmt, params = conn.calls[0]
    assert "INSERT INTO \"weftlyflow_vectors\"" in stmt
    assert params[0] == "r1"
    assert params[1] == "ns"
    assert params[2] == "[1.0,0.0]"
    assert out[0][0].json["dimensions"] == 2


async def test_upsert_requires_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(operation="upsert", vector=[1.0])
    with pytest.raises(NodeExecutionError, match="'id' is required"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])


async def test_upsert_rejects_non_numeric_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(operation="upsert", id="r1", vector=[1.0, "bad"])
    with pytest.raises(NodeExecutionError, match="must be a number"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])


# --- query -----------------------------------------------------------


async def test_query_maps_rows_to_matches_with_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection(
        fetch_queue=[[("a", {"doc": "east"}, 0.0), ("b", {"doc": "n"}, 1.0)]],
    )
    _install_fake(monkeypatch, conn)
    node = _node(
        operation="query", namespace="default",
        vector=[1.0, 0.0], top_k=2, metric="cosine",
    )
    out = await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
    payload = out[0][0].json
    assert payload["count"] == 2
    # cosine distance 0.0 -> score 1.0; distance 1.0 -> score 0.0
    assert payload["matches"][0] == {
        "id": "a", "payload": {"doc": "east"}, "score": 1.0,
    }
    assert payload["matches"][1]["score"] == 0.0


async def test_query_euclidean_negates_distance_for_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection(fetch_queue=[[("a", {}, 2.5)]])
    _install_fake(monkeypatch, conn)
    node = _node(
        operation="query", vector=[0.0], top_k=1, metric="euclidean",
    )
    out = await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
    assert out[0][0].json["matches"][0]["score"] == -2.5


async def test_query_rejects_unknown_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(operation="query", vector=[1.0], metric="bogus")
    with pytest.raises(NodeExecutionError, match="metric"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])


async def test_query_rejects_non_positive_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(operation="query", vector=[1.0], top_k=0)
    with pytest.raises(NodeExecutionError, match="top_k"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])


# --- delete / clear --------------------------------------------------


async def test_delete_reports_deleted_flag_when_row_affected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection(rowcount_queue=[1])
    _install_fake(monkeypatch, conn)
    node = _node(operation="delete", namespace="ns", id="r1")
    out = await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
    assert out[0][0].json["deleted"] is True
    assert conn.calls[0][1] == ("r1", "ns")


async def test_delete_reports_false_when_no_rows_affected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection(rowcount_queue=[0])
    _install_fake(monkeypatch, conn)
    node = _node(operation="delete", id="missing")
    out = await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
    assert out[0][0].json["deleted"] is False


async def test_clear_returns_affected_row_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection(rowcount_queue=[7])
    _install_fake(monkeypatch, conn)
    node = _node(operation="clear", namespace="ns")
    out = await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
    assert out[0][0].json == {
        "operation": "clear",
        "table": "weftlyflow_vectors",
        "namespace": "ns",
        "cleared": 7,
    }


async def test_rejects_unknown_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(operation="nope")
    with pytest.raises(NodeExecutionError, match="unsupported operation"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])


async def test_rejects_injection_in_table_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, _FakeConnection())
    node = _node(
        operation="clear", namespace="ns",
        table='vecs"; DROP TABLE users; --',
    )
    with pytest.raises(NodeExecutionError, match="'table'"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])


async def test_empty_items_still_emits_one_default_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection(rowcount_queue=[0])
    _install_fake(monkeypatch, conn)
    node = _node(operation="clear")
    out = await VectorPgvectorNode().execute(_ctx_for(node), [])
    assert len(out[0]) == 1
    assert out[0][0].json["operation"] == "clear"


async def test_database_error_during_execute_is_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ErrorCursor(_FakeCursor):
        async def execute(
            self, stmt: str, params: tuple[Any, ...] = (),
        ) -> None:
            raise psycopg.errors.UndefinedTable("relation does not exist")

    class _ErrorConn(_FakeConnection):
        def cursor(self) -> _FakeCursor:
            return _ErrorCursor(self, fetch=[], rowcount=0)

    _install_fake(monkeypatch, _ErrorConn())
    node = _node(operation="clear")
    with pytest.raises(NodeExecutionError, match="database error"):
        await VectorPgvectorNode().execute(_ctx_for(node), [Item()])
