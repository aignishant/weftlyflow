"""Unit tests for :class:`weftlyflow.webhooks.registry.WebhookRegistry`."""

from __future__ import annotations

import pytest

from weftlyflow.webhooks import (
    UnsupportedMethodError,
    WebhookConflictError,
    WebhookEntry,
    WebhookRegistry,
)


def _entry(
    *,
    id_: str = "wh_1",
    workflow_id: str = "wf_1",
    node_id: str = "node_1",
    project_id: str = "pr_1",
    path: str = "demo/hook",
    method: str = "POST",
) -> WebhookEntry:
    return WebhookEntry(
        id=id_,
        workflow_id=workflow_id,
        node_id=node_id,
        project_id=project_id,
        path=path,
        method=method,
    )


def test_register_and_match_round_trip() -> None:
    reg = WebhookRegistry()
    entry = _entry()

    reg.register(entry)
    hit = reg.match("/demo/hook", "post")

    assert hit is not None
    assert hit.workflow_id == "wf_1"
    assert hit.method == "POST"
    assert hit.path == "demo/hook"


def test_match_is_none_for_unknown_path() -> None:
    reg = WebhookRegistry()
    assert reg.match("/missing", "GET") is None


def test_match_returns_none_for_unparseable_path() -> None:
    reg = WebhookRegistry()
    # All-whitespace normalises to empty which is a ValueError — handled.
    assert reg.match("/", "POST") is None


def test_register_rejects_conflict_on_same_path_method() -> None:
    reg = WebhookRegistry()
    reg.register(_entry(id_="wh_1"))
    with pytest.raises(WebhookConflictError):
        reg.register(_entry(id_="wh_2", workflow_id="wf_2"))


def test_register_with_same_id_is_idempotent() -> None:
    reg = WebhookRegistry()
    entry = _entry()
    reg.register(entry)
    reg.register(entry)  # same id → no conflict
    assert len(reg.all_entries()) == 1


def test_register_rejects_unsupported_method() -> None:
    reg = WebhookRegistry()
    with pytest.raises(UnsupportedMethodError):
        reg.register(_entry(method="TRACE"))


def test_unregister_removes_entry() -> None:
    reg = WebhookRegistry()
    reg.register(_entry())
    removed = reg.unregister("demo/hook", "POST")
    assert removed is not None
    assert reg.match("demo/hook", "POST") is None


def test_unregister_workflow_drops_every_entry() -> None:
    reg = WebhookRegistry()
    reg.register(_entry(id_="wh_1", path="a"))
    reg.register(_entry(id_="wh_2", path="b", method="GET"))
    reg.register(_entry(id_="wh_3", path="c", workflow_id="wf_other"))

    removed = reg.unregister_workflow("wf_1")

    assert {entry.id for entry in removed} == {"wh_1", "wh_2"}
    remaining = {entry.id for entry in reg.all_entries()}
    assert remaining == {"wh_3"}


def test_load_replaces_cache() -> None:
    reg = WebhookRegistry()
    reg.register(_entry(path="one"))
    size = reg.load([_entry(id_="wh_a", path="two"), _entry(id_="wh_b", path="three")])
    assert size == 2
    assert reg.match("one", "POST") is None
    assert reg.match("two", "POST") is not None


def test_method_is_case_insensitive_on_register_and_match() -> None:
    reg = WebhookRegistry()
    reg.register(_entry(method="post"))
    assert reg.match("demo/hook", "POST") is not None
    assert reg.match("demo/hook", "post") is not None


def test_list_for_workflow_returns_only_matching_entries() -> None:
    reg = WebhookRegistry()
    reg.register(_entry(id_="wh_1", path="a", workflow_id="wf_1"))
    reg.register(_entry(id_="wh_2", path="b", workflow_id="wf_2"))
    assert {e.id for e in reg.list_for_workflow("wf_1")} == {"wh_1"}
    assert {e.id for e in reg.list_for_workflow("wf_2")} == {"wh_2"}
