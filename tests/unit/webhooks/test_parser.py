"""Unit tests for :func:`weftlyflow.webhooks.parser.parse_request`."""

from __future__ import annotations

from weftlyflow.webhooks.parser import parse_request


def test_parses_json_body_when_content_type_is_json() -> None:
    parsed = parse_request(
        method="POST",
        path="hook",
        headers=[("Content-Type", "application/json")],
        query_items=[],
        body=b'{"hello": "world"}',
    )
    assert parsed.body == {"hello": "world"}
    assert parsed.method == "POST"


def test_falls_back_to_raw_when_json_is_malformed() -> None:
    parsed = parse_request(
        method="POST",
        path="hook",
        headers=[("content-type", "application/json")],
        query_items=[],
        body=b"not json",
    )
    assert parsed.body == {"raw": "not json"}


def test_empty_body_returns_none() -> None:
    parsed = parse_request(
        method="GET",
        path="hook",
        headers=[],
        query_items=[],
        body=b"",
    )
    assert parsed.body is None


def test_query_multi_values_preserved_in_query_all() -> None:
    parsed = parse_request(
        method="GET",
        path="hook",
        headers=[],
        query_items=[("tag", "a"), ("tag", "b"), ("q", "hello")],
        body=b"",
    )
    assert parsed.query_all == {"tag": ["a", "b"], "q": ["hello"]}
    # Flat view keeps the last value — matches typical JSON intuition.
    assert parsed.query == {"tag": "b", "q": "hello"}


def test_headers_are_lower_cased_and_joined() -> None:
    parsed = parse_request(
        method="GET",
        path="hook",
        headers=[("X-Duplicated", "a"), ("X-Duplicated", "b")],
        query_items=[],
        body=b"",
    )
    assert parsed.headers == {"x-duplicated": "a, b"}


def test_non_json_text_body_wrapped_as_raw() -> None:
    parsed = parse_request(
        method="POST",
        path="hook",
        headers=[("content-type", "text/plain")],
        query_items=[],
        body=b"plain text",
    )
    assert parsed.body == {"raw": "plain text"}


def test_vendor_json_media_type_still_parsed() -> None:
    parsed = parse_request(
        method="POST",
        path="hook",
        headers=[("content-type", "application/vnd.github+json")],
        query_items=[],
        body=b'{"x": 1}',
    )
    assert parsed.body == {"x": 1}
