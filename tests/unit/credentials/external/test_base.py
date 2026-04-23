"""Unit tests for reference parsing."""

from __future__ import annotations

import pytest

from weftlyflow.credentials.external.base import (
    MalformedSecretReferenceError,
    parse_reference,
)


def test_parse_reference_without_field() -> None:
    ref = parse_reference("env:SLACK_TOKEN")
    assert ref.scheme == "env"
    assert ref.path == "SLACK_TOKEN"
    assert ref.field is None
    assert ref.raw == "env:SLACK_TOKEN"


def test_parse_reference_with_field() -> None:
    ref = parse_reference("vault:kv/data/slack#token")
    assert ref.scheme == "vault"
    assert ref.path == "kv/data/slack"
    assert ref.field == "token"
    assert ref.raw == "vault:kv/data/slack#token"


def test_parse_reference_lowercases_scheme() -> None:
    assert parse_reference("ENV:FOO").scheme == "env"


def test_parse_reference_rejects_empty_input() -> None:
    with pytest.raises(MalformedSecretReferenceError):
        parse_reference("")


def test_parse_reference_rejects_missing_colon() -> None:
    with pytest.raises(MalformedSecretReferenceError):
        parse_reference("envSLACK_TOKEN")


def test_parse_reference_rejects_empty_path() -> None:
    with pytest.raises(MalformedSecretReferenceError):
        parse_reference("env:")


def test_parse_reference_rejects_empty_scheme() -> None:
    with pytest.raises(MalformedSecretReferenceError):
        parse_reference(":FOO")


def test_parse_reference_keeps_empty_field_as_none() -> None:
    # "env:FOO#" — field fragment is empty; treat as no field at all.
    ref = parse_reference("env:FOO#")
    assert ref.field == ""
