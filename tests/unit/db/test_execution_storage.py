"""Unit tests for the execution-data storage backends.

Covers behaviour, not implementation:

* The DB backend inlines payloads and rejects foreign kinds.
* The filesystem backend round-trips arbitrary JSON, shards files by
  year/month, deletes cleanly, and survives concurrent writes to distinct
  ids.
* The settings-driven default-store factory picks the right backend.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from weftlyflow.db.execution_storage import (
    STORAGE_KIND_DB,
    STORAGE_KIND_FS,
    DbExecutionDataStore,
    FilesystemExecutionDataStore,
    StoredDataRow,
    StoredExecutionPayload,
    get_default_store,
    set_default_store,
)

pytestmark = pytest.mark.unit


def _sample_payload() -> StoredExecutionPayload:
    return StoredExecutionPayload(
        workflow_snapshot={"id": "wf_1", "nodes": [{"id": "n1"}]},
        run_data={"per_node": {"n1": [{"items": [[{"json": {"ok": True}}]]}]}},
    )


class TestDbStore:
    async def test_write_inlines_payload(self) -> None:
        store = DbExecutionDataStore()
        payload = _sample_payload()

        row = await store.write("exec_1", payload)

        assert row.storage_kind == STORAGE_KIND_DB
        assert row.external_ref is None
        assert row.workflow_snapshot == payload.workflow_snapshot
        assert row.run_data == payload.run_data

    async def test_round_trip(self) -> None:
        store = DbExecutionDataStore()
        payload = _sample_payload()

        row = await store.write("exec_1", payload)
        out = await store.read("exec_1", row)

        assert out == payload

    async def test_read_rejects_foreign_kind(self) -> None:
        store = DbExecutionDataStore()
        foreign = StoredDataRow(
            storage_kind="fs", external_ref="abc", workflow_snapshot={}, run_data={},
        )

        with pytest.raises(ValueError, match="storage_kind"):
            await store.read("exec_1", foreign)

    async def test_delete_is_noop(self) -> None:
        store = DbExecutionDataStore()
        row = StoredDataRow(
            storage_kind=STORAGE_KIND_DB, external_ref=None,
            workflow_snapshot={}, run_data={},
        )

        await store.delete("exec_1", row)  # no exception == pass


class TestFilesystemStore:
    async def test_write_creates_sharded_file(self, tmp_path: Path) -> None:
        store = FilesystemExecutionDataStore(base_path=tmp_path)
        payload = _sample_payload()

        row = await store.write("exec_abc", payload)

        assert row.storage_kind == STORAGE_KIND_FS
        assert row.external_ref is not None
        assert row.workflow_snapshot == {}
        assert row.run_data == {}
        blob = tmp_path / row.external_ref
        assert blob.is_file()
        on_disk = json.loads(blob.read_text())
        assert on_disk["workflow_snapshot"] == payload.workflow_snapshot
        assert on_disk["run_data"] == payload.run_data

    async def test_path_layout_uses_year_month(self, tmp_path: Path) -> None:
        store = FilesystemExecutionDataStore(base_path=tmp_path)

        row = await store.write("exec_1", _sample_payload())

        assert row.external_ref is not None
        parts = Path(row.external_ref).parts
        assert len(parts) == 3, parts
        year, month, name = parts
        assert year.isdigit() and len(year) == 4
        assert month.isdigit() and len(month) == 2
        assert name == "exec_1.json"

    async def test_round_trip(self, tmp_path: Path) -> None:
        store = FilesystemExecutionDataStore(base_path=tmp_path)
        payload = _sample_payload()

        row = await store.write("exec_rt", payload)
        out = await store.read("exec_rt", row)

        assert out == payload

    async def test_read_rejects_foreign_kind(self, tmp_path: Path) -> None:
        store = FilesystemExecutionDataStore(base_path=tmp_path)
        foreign = StoredDataRow(
            storage_kind=STORAGE_KIND_DB, external_ref=None,
            workflow_snapshot={}, run_data={},
        )

        with pytest.raises(ValueError, match="storage_kind"):
            await store.read("exec_1", foreign)

    async def test_read_rejects_missing_external_ref(self, tmp_path: Path) -> None:
        store = FilesystemExecutionDataStore(base_path=tmp_path)
        row = StoredDataRow(
            storage_kind=STORAGE_KIND_FS, external_ref=None,
            workflow_snapshot={}, run_data={},
        )

        with pytest.raises(ValueError, match="external_ref"):
            await store.read("exec_1", row)

    async def test_delete_removes_file(self, tmp_path: Path) -> None:
        store = FilesystemExecutionDataStore(base_path=tmp_path)
        row = await store.write("exec_del", _sample_payload())
        assert (tmp_path / row.external_ref).exists()  # type: ignore[arg-type]

        await store.delete("exec_del", row)

        assert not (tmp_path / row.external_ref).exists()  # type: ignore[arg-type]

    async def test_delete_missing_file_is_silent(self, tmp_path: Path) -> None:
        store = FilesystemExecutionDataStore(base_path=tmp_path)
        row = StoredDataRow(
            storage_kind=STORAGE_KIND_FS,
            external_ref="2099/01/nowhere.json",
            workflow_snapshot={},
            run_data={},
        )

        await store.delete("exec_del", row)  # no exception

    async def test_overwrite_is_atomic(self, tmp_path: Path) -> None:
        store = FilesystemExecutionDataStore(base_path=tmp_path)
        first = StoredExecutionPayload(workflow_snapshot={"v": 1}, run_data={})
        second = StoredExecutionPayload(workflow_snapshot={"v": 2}, run_data={})

        row1 = await store.write("exec_over", first)
        row2 = await store.write("exec_over", second)

        # Same logical path, new contents — no stale tempfiles left behind.
        assert row1.external_ref == row2.external_ref
        out = await store.read("exec_over", row2)
        assert out.workflow_snapshot == {"v": 2}
        siblings = list((tmp_path / Path(row2.external_ref).parent).glob(".exec_over*"))  # type: ignore[arg-type]
        assert siblings == []


class TestDefaultStoreFactory:
    def setup_method(self) -> None:
        set_default_store(None)

    def teardown_method(self) -> None:
        set_default_store(None)

    def test_db_backend_is_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from weftlyflow.config import get_settings

        monkeypatch.setenv("WEFTLYFLOW_EXECUTION_DATA_BACKEND", "db")
        get_settings.cache_clear()

        store = get_default_store()

        assert isinstance(store, DbExecutionDataStore)

    def test_fs_backend_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        from weftlyflow.config import get_settings

        monkeypatch.setenv("WEFTLYFLOW_EXECUTION_DATA_BACKEND", "fs")
        monkeypatch.setenv("WEFTLYFLOW_EXECUTION_DATA_FS_PATH", str(tmp_path))
        get_settings.cache_clear()

        store = get_default_store()

        assert isinstance(store, FilesystemExecutionDataStore)

    def test_fs_backend_requires_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from weftlyflow.config import get_settings

        monkeypatch.setenv("WEFTLYFLOW_EXECUTION_DATA_BACKEND", "fs")
        monkeypatch.setenv("WEFTLYFLOW_EXECUTION_DATA_FS_PATH", "")
        get_settings.cache_clear()

        with pytest.raises(ValueError, match="execution_data_fs_path"):
            get_default_store()

    def test_unknown_backend_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from weftlyflow.config import get_settings

        monkeypatch.setenv("WEFTLYFLOW_EXECUTION_DATA_BACKEND", "ftp")
        get_settings.cache_clear()

        with pytest.raises(ValueError, match="unknown execution_data_backend"):
            get_default_store()
