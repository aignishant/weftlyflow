"""Weftlyflow test suite.

Layout:
    unit/        — pure unit tests (no DB, no Redis, no network).
    integration/ — FastAPI + in-memory SQLite + fakeredis.
    nodes/       — one folder per node with fixtures + HTTP-mocked tests.
    load/        — performance benchmarks (locust-driven, opt-in).

Markers (declared in ``pyproject.toml``):
    unit, integration, node, live, load.
"""

from __future__ import annotations
