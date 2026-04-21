# Changelog

All notable user-facing changes. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Phase 0 bootstrap: repo layout, `pyproject.toml`, `Makefile`, `Dockerfile`s, `docker-compose.yml`, pre-commit config.
- Project identity: **Weftlyflow**, clean-room Python replica of n8n's architecture.
- `IMPLEMENTATION_BIBLE.md` — the canonical design document.
- Domain dataclasses: `Workflow`, `Node`, `Connection`, `Execution`, `Item`, `RunData`, `NodeSpec`.
- FastAPI skeleton with `/healthz`, `/readyz`.
- Celery skeleton.
- `.claude/` folder adapted from `low-spec-2` — 9 agents, 6 skills, 6 hooks, MCP config.
- mkdocs-material + mkdocstrings + auto-generated API reference.
- Smoke tests passing: `make lint && make typecheck && make test && make docs-build`.
