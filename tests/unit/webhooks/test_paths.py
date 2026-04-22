"""Unit tests for :mod:`weftlyflow.webhooks.paths`."""

from __future__ import annotations

import pytest

from weftlyflow.webhooks.paths import dynamic_path, normalise_path, static_path


def test_normalise_strips_leading_and_trailing_slashes() -> None:
    assert normalise_path("/foo/bar/") == "foo/bar"


def test_normalise_rejects_empty_path() -> None:
    with pytest.raises(ValueError):
        normalise_path("  ")


def test_normalise_collapses_invalid_chars() -> None:
    assert normalise_path("foo/bar baz") == "foo/bar-baz"


def test_static_path_uses_user_input_when_provided() -> None:
    assert static_path("wf_1", "node_1", "custom/path") == "custom/path"


def test_static_path_falls_back_to_ids() -> None:
    assert static_path("wf_1", "node_1", None) == "wf_1/node_1"
    assert static_path("wf_1", "node_1", "   ") == "wf_1/node_1"


def test_dynamic_path_has_u_prefix() -> None:
    path = dynamic_path()
    assert path.startswith("u/")
    assert len(path) > len("u/")
