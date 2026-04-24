"""In-process vector store backed by workflow ``static_data``.

Complements the RAG primitives shipped earlier in Phase 7
(``text_splitter`` + OpenAI ``create_embedding``): nothing in here
talks to a real vector database, which keeps the node self-contained
and lets users build a working retrieval loop with no external infra.
Real backends (Qdrant, pgvector, Pinecone) will live in sibling nodes
with the same operation surface.

Records are stored under
``static_data[VECTOR_NAMESPACE][namespace] = list[Record]`` where a
record is a dict of the shape:

``{"id": str, "vector": list[float], "payload": dict[str, Any]}``

The store exposes pure functions - they read and write the
``static_data`` dict you hand them, so unit tests can exercise them
without constructing an :class:`ExecutionContext`.
"""

from __future__ import annotations

import math
from typing import Any, Final

VECTOR_NAMESPACE: Final[str] = "_vector_memory"

METRIC_COSINE: Final[str] = "cosine"
METRIC_DOT: Final[str] = "dot"
METRIC_EUCLIDEAN: Final[str] = "euclidean"
_SUPPORTED_METRICS: Final[frozenset[str]] = frozenset(
    {METRIC_COSINE, METRIC_DOT, METRIC_EUCLIDEAN},
)


Record = dict[str, Any]


def _records(
    static_data: dict[str, Any], namespace: str,
) -> list[Record]:
    """Return the mutable record list for ``namespace``, creating on demand."""
    bucket = static_data.get(VECTOR_NAMESPACE)
    if not isinstance(bucket, dict):
        bucket = {}
        static_data[VECTOR_NAMESPACE] = bucket
    existing = bucket.get(namespace)
    if not isinstance(existing, list):
        existing = []
        bucket[namespace] = existing
    return existing


def upsert(
    static_data: dict[str, Any],
    namespace: str,
    record_id: str,
    vector: list[float],
    payload: dict[str, Any],
) -> Record:
    """Insert or replace a single record in ``namespace``.

    Returns the stored record (a fresh dict - the caller gets a copy).
    """
    records = _records(static_data, namespace)
    entry: Record = {
        "id": record_id,
        "vector": list(vector),
        "payload": dict(payload),
    }
    for idx, existing in enumerate(records):
        if existing.get("id") == record_id:
            records[idx] = entry
            return dict(entry)
    records.append(entry)
    return dict(entry)


def delete(
    static_data: dict[str, Any], namespace: str, record_id: str,
) -> bool:
    """Remove a record by id. Returns True when a row was deleted."""
    records = _records(static_data, namespace)
    for idx, existing in enumerate(records):
        if existing.get("id") == record_id:
            records.pop(idx)
            return True
    return False


def clear(static_data: dict[str, Any], namespace: str) -> int:
    """Drop every record in ``namespace``. Returns the count removed."""
    records = _records(static_data, namespace)
    count = len(records)
    records.clear()
    return count


def query(
    static_data: dict[str, Any],
    namespace: str,
    vector: list[float],
    *,
    top_k: int,
    metric: str,
) -> list[dict[str, Any]]:
    """Return the top-``k`` records ranked by similarity to ``vector``.

    Each result dict contains ``id``, ``payload``, and ``score``. For
    ``cosine`` and ``dot``, higher is better; for ``euclidean`` the
    score is the *negated* distance so that higher always means "more
    similar" across metrics.
    """
    if metric not in _SUPPORTED_METRICS:
        msg = f"unsupported metric {metric!r}"
        raise ValueError(msg)
    if top_k <= 0:
        msg = f"top_k must be > 0, got {top_k}"
        raise ValueError(msg)
    records = _records(static_data, namespace)
    scored: list[tuple[float, Record]] = []
    for record in records:
        stored = record.get("vector")
        if not isinstance(stored, list) or len(stored) != len(vector):
            continue
        score = _score(stored, vector, metric)
        scored.append((score, record))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "id": record.get("id"),
            "payload": dict(record.get("payload") or {}),
            "score": score,
        }
        for score, record in scored[:top_k]
    ]


def _score(a: list[float], b: list[float], metric: str) -> float:
    if metric == METRIC_DOT:
        return _dot(a, b)
    if metric == METRIC_EUCLIDEAN:
        return -math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))
    # cosine
    dot = _dot(a, b)
    norm_a = math.sqrt(_dot(a, a))
    norm_b = math.sqrt(_dot(b, b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
