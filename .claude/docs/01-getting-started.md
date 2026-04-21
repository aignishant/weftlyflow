# 01 — Getting started

## First 10 minutes

1. Read `/IMPLEMENTATION_BIBLE.md` §1–§6 (identity, glossary, stack, layout).
2. Skim `.claude/CLAUDE.md` — the non-negotiables.
3. `/load-context` — quick situational brief.
4. `/doctor` then `/mcp` — verify hooks and MCP servers.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs,ai]"
pre-commit install
cp .env.example .env                         # set WEFTLYFLOW_ENCRYPTION_KEY and secrets
cp .claude/settings.local.json.example .claude/settings.local.json
```

## Run Phase-0 smoke tests

```bash
make lint         # should pass
make typecheck    # should pass
make test         # smoke tests should pass
make docs-build   # static docs site should build
```

If any of these fail on a fresh clone, the bootstrap is broken — open an issue.

## Running the stack

```bash
# option A — local processes
make dev-api          # :5678
make dev-worker       # separate shell
cd frontend && npm run dev    # :5173

# option B — docker
make docker-up
```

## Verifying

```bash
curl http://localhost:5678/healthz
# {"status":"ok","version":"0.1.0a0"}
```
