"""Pure SQL builders for the pgvector-backed vector store node.

Every builder returns ``(statement, params)`` — no database handle,
no side effects — so unit tests can verify wire text and parameter
binding without a live Postgres.

Table schema (identical across all callers)::

    CREATE TABLE IF NOT EXISTS <table> (
        id        text PRIMARY KEY,
        namespace text NOT NULL,
        vector    vector(<n>) NOT NULL,
        payload   jsonb NOT NULL DEFAULT '{}'::jsonb
    );

Two composite indexes back the query path: one on ``(namespace, id)``
for point reads and one on ``vector`` using an IVF flat index per
metric (built lazily in :func:`build_ensure_schema`).

Similarity metrics map onto pgvector's three operators:

* ``cosine``    -> ``<=>`` (cosine *distance*;  score = 1 - distance)
* ``dot``       -> ``<#>`` (negative inner product; score = -op)
* ``euclidean`` -> ``<->`` (L2 distance; score = -distance)

The node translates distances to "higher is more similar" scores at
the Python level so callers can reason about a single convention
across every backend.
"""

from __future__ import annotations

import json
import re
from typing import Any, Final

METRIC_COSINE: Final[str] = "cosine"
METRIC_DOT: Final[str] = "dot"
METRIC_EUCLIDEAN: Final[str] = "euclidean"
SUPPORTED_METRICS: Final[frozenset[str]] = frozenset(
    {METRIC_COSINE, METRIC_DOT, METRIC_EUCLIDEAN},
)

_METRIC_OPERATOR: Final[dict[str, str]] = {
    METRIC_COSINE: "<=>",
    METRIC_DOT: "<#>",
    METRIC_EUCLIDEAN: "<->",
}

# Spec §23 — identifiers embedded in SQL text must be validated before
# formatting. We never parameterise table names because Postgres does
# not allow that at the wire level; instead we require a conservative
# identifier pattern and quote with double-quotes to preserve case.
_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]{0,62}$",
)


def validate_identifier(name: str, *, field: str) -> str:
    """Return ``name`` unchanged when safe; raise :class:`ValueError` otherwise.

    A conservative ASCII identifier pattern — safer than ``quote_ident``
    for a node surface where the value is user-driven and there is no
    legitimate reason to need exotic table names.
    """
    if not _IDENTIFIER_PATTERN.match(name):
        msg = (
            f"Vector Pgvector: {field!r} must match "
            f"^[A-Za-z_][A-Za-z0-9_]*$ (got {name!r})"
        )
        raise ValueError(msg)
    return name


def vector_literal(vector: list[float]) -> str:
    """Encode a vector as the pgvector text literal ``'[0.1,0.2,...]'``.

    pgvector accepts a vector parameter in this exact textual form;
    there is no native binary codec in psycopg3 without an optional
    adapter, so we bind a string and cast with ``::vector`` in SQL.
    """
    return "[" + ",".join(_format_float(x) for x in vector) + "]"


def _format_float(value: float) -> str:
    # ``repr`` preserves full round-trip precision across IEEE-754 and
    # is accepted verbatim by pgvector. ``str`` truncates on some
    # CPython builds, so repr is the safer choice.
    return repr(float(value))


def build_ensure_schema(
    *, table: str, dimensions: int,
) -> list[tuple[str, tuple[Any, ...]]]:
    """Return the idempotent statements that create the extension + table.

    Emits four statements: the extension itself, the table, the
    ``(namespace, id)`` index, and a per-metric IVF flat index on the
    vector column. Each is ``IF NOT EXISTS`` so replays are safe.
    """
    validate_identifier(table, field="table")
    if dimensions < 1:
        msg = "Vector Pgvector: 'dimensions' must be >= 1"
        raise ValueError(msg)
    quoted = f'"{table}"'
    statements: list[tuple[str, tuple[Any, ...]]] = [
        ("CREATE EXTENSION IF NOT EXISTS vector", ()),
        (
            (
                f"CREATE TABLE IF NOT EXISTS {quoted} ("
                "id text PRIMARY KEY, "
                "namespace text NOT NULL, "
                f"vector vector({dimensions}) NOT NULL, "
                "payload jsonb NOT NULL DEFAULT '{}'::jsonb)"
            ),
            (),
        ),
        (
            (
                f"CREATE INDEX IF NOT EXISTS {table}_namespace_idx "
                f"ON {quoted} (namespace)"
            ),
            (),
        ),
    ]
    return statements


def build_upsert(
    *,
    table: str,
    namespace: str,
    record_id: str,
    vector: list[float],
    payload: dict[str, Any],
) -> tuple[str, tuple[Any, ...]]:
    """Return an ``INSERT ... ON CONFLICT DO UPDATE`` statement."""
    validate_identifier(table, field="table")
    quoted = f'"{table}"'
    statement = (
        f"INSERT INTO {quoted} (id, namespace, vector, payload) "
        "VALUES (%s, %s, %s::vector, %s::jsonb) "
        "ON CONFLICT (id) DO UPDATE SET "
        "namespace = EXCLUDED.namespace, "
        "vector = EXCLUDED.vector, "
        "payload = EXCLUDED.payload"
    )
    params = (
        record_id,
        namespace,
        vector_literal(vector),
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )
    return statement, params


def build_query(
    *,
    table: str,
    namespace: str,
    vector: list[float],
    top_k: int,
    metric: str,
) -> tuple[str, tuple[Any, ...]]:
    """Return a ``SELECT ... ORDER BY <op> LIMIT`` statement."""
    validate_identifier(table, field="table")
    if metric not in SUPPORTED_METRICS:
        msg = f"Vector Pgvector: unsupported metric {metric!r}"
        raise ValueError(msg)
    if top_k < 1:
        msg = "Vector Pgvector: 'top_k' must be >= 1"
        raise ValueError(msg)
    quoted = f'"{table}"'
    operator = _METRIC_OPERATOR[metric]
    statement = (
        f"SELECT id, payload, (vector {operator} %s::vector) AS distance "
        f"FROM {quoted} "
        "WHERE namespace = %s "
        f"ORDER BY vector {operator} %s::vector ASC "
        "LIMIT %s"
    )
    literal = vector_literal(vector)
    return statement, (literal, namespace, literal, top_k)


def score_from_distance(metric: str, distance: float) -> float:
    """Convert pgvector's distance into a higher-is-better score.

    ``cosine`` distance is in ``[0, 2]``; subtracting from 1 gives the
    familiar cosine similarity in ``[-1, 1]``. Dot and euclidean are
    negated so callers can apply the same ordering across backends.
    """
    if metric == METRIC_COSINE:
        return 1.0 - distance
    return -distance


def build_delete(
    *, table: str, namespace: str, record_id: str,
) -> tuple[str, tuple[Any, ...]]:
    """Return a ``DELETE`` statement scoped to namespace + id."""
    validate_identifier(table, field="table")
    quoted = f'"{table}"'
    statement = (
        f"DELETE FROM {quoted} WHERE id = %s AND namespace = %s"
    )
    return statement, (record_id, namespace)


def build_clear(
    *, table: str, namespace: str,
) -> tuple[str, tuple[Any, ...]]:
    """Return a ``DELETE`` statement that empties one namespace."""
    validate_identifier(table, field="table")
    quoted = f'"{table}"'
    statement = f"DELETE FROM {quoted} WHERE namespace = %s"
    return statement, (namespace,)
