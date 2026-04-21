"""Tests for :mod:`weftlyflow.nodes.utils.paths`."""

from __future__ import annotations

import pytest

from weftlyflow.nodes.utils.paths import del_path, get_path, set_path


def test_get_path_returns_nested_value():
    data = {"a": {"b": {"c": 42}}}
    assert get_path(data, "a.b.c") == 42


def test_get_path_returns_default_when_missing():
    assert get_path({"a": {}}, "a.missing", default="fallback") == "fallback"


def test_get_path_indexes_into_list():
    data = {"items": [{"v": 1}, {"v": 2}]}
    assert get_path(data, "items.1.v") == 2


def test_set_path_creates_intermediate_dicts():
    data: dict = {}
    set_path(data, "a.b.c", 99)
    assert data == {"a": {"b": {"c": 99}}}


def test_set_path_overwrites_non_dict():
    data = {"a": 1}
    set_path(data, "a.b", 2)
    assert data == {"a": {"b": 2}}


def test_del_path_returns_false_when_missing():
    assert del_path({}, "a.b") is False


def test_del_path_removes_deep_key():
    data = {"a": {"b": 1, "c": 2}}
    assert del_path(data, "a.b") is True
    assert data == {"a": {"c": 2}}


def test_empty_path_raises():
    with pytest.raises(ValueError):
        get_path({}, "")


def test_empty_segment_raises():
    with pytest.raises(ValueError):
        set_path({}, "a..b", 1)
