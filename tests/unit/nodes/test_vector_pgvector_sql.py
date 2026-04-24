"""Unit tests for the pure SQL builders in ``vector_pgvector.sql``.

The builders are intentionally side-effect free: every test asserts on
the SQL text and parameter tuple without opening a database connection.
"""

from __future__ import annotations

import json

import pytest

from weftlyflow.nodes.ai.vector_pgvector.sql import (
    METRIC_COSINE,
    METRIC_DOT,
    METRIC_EUCLIDEAN,
    build_clear,
    build_delete,
    build_ensure_schema,
    build_query,
    build_upsert,
    score_from_distance,
    validate_identifier,
    vector_literal,
)


def test_validate_identifier_accepts_snake_case() -> None:
    assert validate_identifier("weftlyflow_vectors", field="table") == (
        "weftlyflow_vectors"
    )


def test_validate_identifier_rejects_leading_digit() -> None:
    with pytest.raises(ValueError, match="must match"):
        validate_identifier("1bad", field="table")


def test_validate_identifier_rejects_sql_injection_attempt() -> None:
    with pytest.raises(ValueError):
        validate_identifier('t"; DROP TABLE users; --', field="table")


def test_validate_identifier_rejects_empty_string() -> None:
    with pytest.raises(ValueError):
        validate_identifier("", field="table")


def test_vector_literal_wraps_floats_in_square_brackets() -> None:
    assert vector_literal([0.1, 0.25, -3.0]) == "[0.1,0.25,-3.0]"


def test_vector_literal_preserves_float_precision() -> None:
    # repr-based formatting must round-trip IEEE-754 floats.
    value = 0.1 + 0.2  # famous 0.30000000000000004
    assert repr(value) in vector_literal([value])


def test_build_ensure_schema_emits_extension_table_and_index() -> None:
    stmts = build_ensure_schema(table="vecs", dimensions=8)
    assert len(stmts) == 3
    assert "CREATE EXTENSION IF NOT EXISTS vector" in stmts[0][0]
    assert "CREATE TABLE IF NOT EXISTS \"vecs\"" in stmts[1][0]
    assert "vector(8)" in stmts[1][0]
    assert "CREATE INDEX IF NOT EXISTS vecs_namespace_idx" in stmts[2][0]
    # No parameters on ensure-schema statements — all static DDL.
    assert all(params == () for _, params in stmts)


def test_build_ensure_schema_rejects_bad_identifier() -> None:
    with pytest.raises(ValueError):
        build_ensure_schema(table="bad table", dimensions=4)


def test_build_ensure_schema_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        build_ensure_schema(table="vecs", dimensions=0)


def test_build_upsert_uses_on_conflict_do_update() -> None:
    stmt, params = build_upsert(
        table="vecs",
        namespace="ns",
        record_id="r1",
        vector=[1.0, 0.0],
        payload={"tag": "east"},
    )
    assert "INSERT INTO \"vecs\"" in stmt
    assert "ON CONFLICT (id) DO UPDATE" in stmt
    assert params[0] == "r1"
    assert params[1] == "ns"
    assert params[2] == "[1.0,0.0]"
    # Payload must be JSON-encoded so ::jsonb casts cleanly.
    assert json.loads(params[3]) == {"tag": "east"}


def test_build_upsert_sorts_payload_keys_for_deterministic_encoding() -> None:
    _, params = build_upsert(
        table="vecs",
        namespace="ns",
        record_id="r1",
        vector=[1.0],
        payload={"b": 2, "a": 1},
    )
    assert params[3] == '{"a": 1, "b": 2}'


def test_build_query_embeds_metric_operator() -> None:
    stmt, params = build_query(
        table="vecs",
        namespace="ns",
        vector=[1.0, 0.0],
        top_k=3,
        metric=METRIC_COSINE,
    )
    assert "<=>" in stmt
    assert "ORDER BY vector <=> %s::vector ASC" in stmt
    assert params == ("[1.0,0.0]", "ns", "[1.0,0.0]", 3)


def test_build_query_uses_negative_inner_product_for_dot() -> None:
    stmt, _ = build_query(
        table="vecs", namespace="ns", vector=[1.0], top_k=1, metric=METRIC_DOT,
    )
    assert "<#>" in stmt


def test_build_query_uses_l2_for_euclidean() -> None:
    stmt, _ = build_query(
        table="vecs", namespace="ns", vector=[1.0],
        top_k=1, metric=METRIC_EUCLIDEAN,
    )
    assert "<->" in stmt


def test_build_query_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="metric"):
        build_query(
            table="vecs", namespace="ns", vector=[1.0], top_k=1, metric="bogus",
        )


def test_build_query_rejects_non_positive_top_k() -> None:
    with pytest.raises(ValueError, match="top_k"):
        build_query(
            table="vecs", namespace="ns", vector=[1.0],
            top_k=0, metric=METRIC_COSINE,
        )


def test_build_delete_scopes_by_id_and_namespace() -> None:
    stmt, params = build_delete(
        table="vecs", namespace="ns", record_id="r1",
    )
    assert "DELETE FROM \"vecs\"" in stmt
    assert "id = %s AND namespace = %s" in stmt
    assert params == ("r1", "ns")


def test_build_clear_deletes_whole_namespace() -> None:
    stmt, params = build_clear(table="vecs", namespace="ns")
    assert "DELETE FROM \"vecs\" WHERE namespace = %s" in stmt
    assert params == ("ns",)


def test_score_from_distance_cosine_inverts_to_similarity() -> None:
    # cosine distance 0 -> similarity 1; distance 2 -> similarity -1
    assert score_from_distance(METRIC_COSINE, 0.0) == 1.0
    assert score_from_distance(METRIC_COSINE, 2.0) == -1.0


def test_score_from_distance_non_cosine_negates_distance() -> None:
    assert score_from_distance(METRIC_DOT, 3.5) == -3.5
    assert score_from_distance(METRIC_EUCLIDEAN, 4.0) == -4.0
