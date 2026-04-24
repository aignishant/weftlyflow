# Coding standards

Quick reference. The authoritative copy lives at `weftlyinfo.md §22`.

## Required

- Module docstring on every `.py`.
- Google-style docstring on every public class/function, with an `Example:` block for non-trivial methods.
- `structlog.get_logger(__name__)` — never `print`.
- `from __future__ import annotations` at the top of every module.
- Absolute imports only; isort orders them.
- `mypy --strict` must pass.
- No file > 400 lines without splitting.
- Google-style pydocstyle (`ruff` rule `D`).

## Layer discipline

`server, worker, webhooks, triggers → engine → nodes, credentials, expression → domain`

`domain/` imports NOTHING from other Weftlyflow subpackages.

## Commits

Conventional Commits. Draft via `/git:commit`.
