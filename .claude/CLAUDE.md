# CLAUDE.md — Weftlyflow project memory

> Auto-loaded into every Claude Code session for this project. Keep under ~200 lines.
> The canonical design document is `/IMPLEMENTATION_BIBLE.md`. This file is the TL;DR.

## Project identity

- **Name:** Weftlyflow
- **Purpose:** Self-hosted workflow automation platform — original-code, clean-room Python re-imagination of n8n's architecture.
- **Working dir:** `/home/nishantgupta/Desktop/ng8`
- **Reference source:** `/home/nishantgupta/Downloads/n8n-master/` — **read for understanding only**. Do not copy code, identifiers, node names, or credential slugs verbatim.
- **Primary language:** Python 3.12 (3.11 supported)
- **Build:** `pip` + `hatch` (PEP 621). Not `poetry`, not `uv`.
- **Test runner:** `pytest` (+ `pytest-asyncio`, `pytest-cov`, `pytest-xdist`, `hypothesis`, `respx`)
- **Lint:** `ruff check` (with `D` pydocstyle). **Format:** `ruff format` + `black` + `isort`.
- **Type-check:** `mypy --strict`.
- **Docs:** `mkdocs-material` + `mkdocstrings[python]` + `mkdocs-gen-files`.
- **Frontend:** Vue 3 + TypeScript + Vite + Pinia + Vue Flow (under `/frontend`). Backend-only PRs do not touch it.

## Architecture at a glance (Python side)

```
src/weftlyflow/
├── domain/         pure dataclasses — no IO
├── db/             SQLAlchemy 2 entities, repositories, Alembic migrations
├── engine/         execution engine (the heart)
├── expression/     {{ ... }} tokenizer + RestrictedPython sandbox
├── nodes/          built-in node plugins (core/, integrations/, ai/)
├── credentials/    credential plugin system + Fernet encryption
├── server/         FastAPI app, routers, schemas
├── webhooks/       webhook registry + HTTP routing
├── triggers/       cron/poll/event lifecycle (APScheduler)
├── worker/         Celery app + tasks (+ sandbox subprocess runner)
├── auth/           argon2, JWT, RBAC, TOTP
├── observability/  structlog, Prometheus, OpenTelemetry
└── utils/          leaf-level helpers
```

Dependency direction (no back-edges):
`server, worker, webhooks, triggers → engine → nodes, credentials, expression → domain`
`db` is used by `server`, `worker`, `triggers`. `domain` imports nothing Weftlyflow-ish.

## Non-negotiable rules

1. **No code copied from n8n.** Read for architecture, then close the file and write from scratch. See `IMPLEMENTATION_BIBLE.md §23`.
2. **Never copy identifiers.** Weftlyflow uses `weftlyflow.http_request`, not `n8n-nodes-base.httpRequest`.
3. **Module docstring on every `.py` file.** File-level purpose, subsystem, cross-ref.
4. **Google-style docstring on every public class/function.** `Example:` block required for non-trivial methods.
5. **Never commit without explicit approval.** Never push directly to `main`/`master`.
6. **Never use `print()` in library code.** Use `structlog.get_logger(__name__)`.
7. **Never hardcode secrets.** Use settings + `.env`.
8. **No file > 400 lines** without refactoring.
9. **Domain layer (`src/weftlyflow/domain/`) imports NOTHING from other Weftlyflow subpackages.** Period.
10. **`mypy --strict` must pass.** No bare `Any` without an inline justification comment.
11. **Every new language/framework introduced gets a cheatsheet in memory.** (User rule.)
12. **Defaults to zero comments.** Docstrings carry the weight. A comment explains only *why*, never *what*.

## Conventions

- Types: `list[int]`, `str | None`, never `Optional[X]` unless forced. `TypedDict` / `Protocol` over `dict[str, Any]`.
- Errors: raise the most specific `WeftlyflowError` subclass. Narrow catches only.
- Async: only at IO boundaries (FastAPI handlers, httpx, SQLAlchemy async). Engine core is async because nodes can be.
- Logging: `log = structlog.get_logger(__name__)`; `log.bind(execution_id=..., node_id=...)` early.
- Imports: absolute only; `from __future__ import annotations` at top of every module; isort `known_first_party = ["weftlyflow"]`.
- Tests: AAA (arrange-act-assert); marker per tier (`unit`, `integration`, `node`, `live`, `load`); one behaviour per test.

## Commands

- `make install` — editable install with `dev`+`docs`+`ai` extras.
- `make dev-api` — reload-mode FastAPI on :5678.
- `make dev-worker`, `make dev-beat` — Celery.
- `make dev-frontend` — Vite on :5173.
- `make lint && make typecheck && make test` — the local CI gate.
- `make docs-serve` — mkdocs on :8000.
- `make db-upgrade`, `make db-revision MSG="..."` — Alembic.

## Where to find things

- Bible: `/IMPLEMENTATION_BIBLE.md`.
- Memory + tech cheatsheets: `/home/nishantgupta/.claude/projects/-home-nishantgupta-Desktop-ng8/memory/`.
- Reference n8n source (read-only): `/home/nishantgupta/Downloads/n8n-master/`.
- `.claude` reference this was adapted from: `/home/nishantgupta/Desktop/Projects/low-spec-2/.claude/`.

## Karpathy Skills — behavioral principles

> Source: https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/CLAUDE.md
> Bias toward caution over speed. For trivial tasks, use judgement.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that YOUR changes made unused; leave pre-existing dead code alone unless asked.
- Test: every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass."
- "Fix the bug" → "Write a test that reproduces it, then make it pass."
- "Refactor X" → "Ensure tests pass before and after."

For multi-step tasks, state a brief plan: `step → verify` per line. Strong success criteria let the agent loop independently.

**Working when:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, clarifying questions come before implementation rather than after mistakes.
