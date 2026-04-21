# Weftlyflow

> Self-hosted workflow automation platform — visual node-graph editor, triggers, polling,
> hundreds of integrations, AI agents. Python backend, Vue 3 frontend.

Weftlyflow is an **independent, clean-room Python implementation** inspired by n8n's
architecture. The canonical project plan lives in
[`IMPLEMENTATION_BIBLE.md`](./IMPLEMENTATION_BIBLE.md) — treat it as the bible.

## Status

Pre-alpha. Phase 0 (bootstrap) in progress. See §24 of the bible for the roadmap.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, Celery + Redis,
  APScheduler, RestrictedPython, structlog, httpx, `cryptography` (Fernet).
- **Frontend:** Vue 3 (Composition API), Pinia, Vue Router, Vue Flow, CodeMirror 6,
  Vite, TypeScript.
- **Tooling:** pip + hatch (PEP 621), ruff, black, mypy --strict, pytest, Playwright,
  pre-commit, mkdocs-material + mkdocstrings.
- **Infra:** Docker + docker-compose; Postgres (prod) / SQLite (dev); Redis.

## Quickstart (dev)

```bash
# backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs]"
cp .env.example .env
make db-upgrade
make dev-api        # http://localhost:5678

# worker (separate shell)
make dev-worker

# frontend (separate shell)
cd frontend && npm install && npm run dev   # http://localhost:5173

# docs (separate shell)
make docs-serve      # http://localhost:8000
```

## Layout

```
src/weftlyflow/        backend Python package
frontend/            Vue 3 + Vite app
docs/                mkdocs source
tests/               backend tests (unit, integration, node, load)
.claude/             Claude Code config (agents, skills, hooks, MCP)
docker/              Dockerfiles per service
alembic/             DB migrations
```

Full tree + rationale: see the bible.

## Licensing & IP

Weftlyflow is original code. It is **not** a fork of n8n. See §23 of the bible for the
clean-room rules that every contribution must follow.

## Contributing

Every new node, credential type, or architectural change follows the contribution
guide (`docs/contributing/`) and must preserve the conventions in §22 of the bible.
