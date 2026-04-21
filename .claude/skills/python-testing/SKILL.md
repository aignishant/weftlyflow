---
name: python-testing
description: Run Weftlyflow pytest suites and interpret failures. Auto-invokes on "run tests", "test this", "why did this test fail", or when pytest output lands in the transcript.
allowed-tools: Read, Grep, Glob, Bash(python -m pytest:*), Bash(make test:*), Bash(make coverage)
---

# Skill: python-testing

## When I fire

- User says: "run tests", "test this", "why did test X fail".
- A pytest traceback appears in the transcript.
- After writing a new test file.

## What I do

1. Pick the narrowest command that covers the change:
   - Node change → `python -m pytest tests/nodes/<slug> -x`
   - Engine/domain change → `python -m pytest tests/unit/<area> -x`
   - Server change → `make test-integration`
   - Whole suite → `make test-all`
2. Run it. Capture stdout/stderr.
3. If green: one-line confirmation + file count + duration.
4. If red: delegate to the `debugger` agent with the traceback. Do not try to fix the bug here.

## Markers quick-ref

| Marker | Command |
|---|---|
| `unit` | `pytest -m unit` |
| `integration` | `make test-integration` |
| `node` | `pytest -m node` |
| `live` | `pytest -m live` (opt-in; hits real APIs) |
| `load` | `pytest -m load` (separate job) |

## Gotchas

- `asyncio_mode = "auto"` in `pyproject.toml` — do NOT add `@pytest.mark.asyncio` by hand.
- fakeredis + in-memory SQLite are the defaults; don't accidentally hit a real Redis.
