# 02 — MCP and plugins

MCP servers are declared in `.claude/.mcp.json`. Each adds tools the model can call.

| Server | Default | Purpose |
|---|---|---|
| `filesystem` | enabled | Scoped local file access. |
| `github` | enabled | Issues / PRs / repo ops. Needs `$GITHUB_TOKEN`. |
| `context7` | enabled | Live docs lookup — FastAPI, SQLAlchemy, Vue, Vue Flow, Celery, RestrictedPython, LangChain. |
| `playwright` | enabled | Headless browser — editor canvas E2E, docs QA. |
| `postgres` | disabled | Read-only access to the dev DB. Enable after `make docker-up`. |
| `redis` | disabled | Inspect Celery queues and leader-election locks. |
| `weftlyflow-tools` | disabled | In-repo MCP exposing Weftlyflow's CLI as tools. Phase 7+. |

## Enabling a disabled server

1. Flip `"disabled": false`.
2. Ensure the env var the server needs is present (`DATABASE_URL`, `REDIS_URL`, `GITHUB_TOKEN`).
3. `/mcp` inside Claude Code — look for a green connection.

## Adding a new server

Edit `.claude/.mcp.json`; restart Claude Code; verify with `/mcp`. Keep tokens in env, never inline.
