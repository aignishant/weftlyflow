# RUN.md — how to run & validate Weftlyflow

This file is the single source of truth for:

1. **Bootstrapping** a fresh clone.
2. **Running** each subsystem locally.
3. **Validating** each phase delivered from `IMPLEMENTATION_BIBLE.md §24`.

Every phase in the bible has a corresponding **validation block** below. When a
phase is claimed complete, run its block and confirm every command in it exits
with status `0`. If any step errors, the phase is **not** done.

Canonical design doc: [`IMPLEMENTATION_BIBLE.md`](./IMPLEMENTATION_BIBLE.md).

---

## 0. Prerequisites (once per machine)

- Python **3.12** (3.11 supported). Check: `python3 --version`.
- `make` on PATH.
- For later phases: Docker + Docker Compose, Node.js 20 + npm (frontend),
  Redis and Postgres (or use `docker compose up -d redis postgres`).

---

## 1. One-time bootstrap

```bash
# from the repo root
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev,docs]'        # editable install + dev + docs extras
cp .env.example .env                # then edit secrets as needed
```

Every subsequent `make` / `pytest` / `ruff` / `mypy` / `mkdocs` invocation in
this file assumes the venv is activated (`source .venv/bin/activate`).

---

## 2. Running locally (per subsystem)

| Goal | Command | URL |
| ---- | ------- | --- |
| API server (reload)  | `make dev-api`       | http://localhost:5678 |
| Celery worker        | `make dev-worker`    | — |
| Celery Beat          | `make dev-beat`      | — |
| Vite frontend        | `make dev-frontend`  | http://localhost:5173 |
| Docs (live-reload)   | `make docs-serve`    | http://localhost:8000 |
| Full stack (Docker)  | `make docker-up`     | http://localhost:5678 |

Health probes (any phase ≥ 0):

```bash
curl -fsS http://localhost:5678/healthz       # liveness
curl -fsS http://localhost:5678/readyz        # readiness
```

---

## 3. Per-phase validation

Each block is the **acceptance gate** for that phase. Paste it in a shell; if
every command exits 0, the phase is signed off.

### Phase 0 — Bootstrap

```bash
make lint        # ruff — no diagnostics
make typecheck   # mypy --strict — 0 errors
make test        # pytest unit suite — all pass
make docs-build  # mkdocs build --strict — site/ produced
```

Extra sanity check:

```bash
python -c "import weftlyflow; print(weftlyflow.__version__)"
python -m weftlyflow version
```

### Phase 1 — Core engine

```bash
make lint && make typecheck
pytest tests/unit/engine -v        # engine-layer unit tests
pytest tests/unit/test_smoke.py    # smoke still passes
```

Smoke program (run from the repo root):

```bash
python - <<'PY'
from weftlyflow.domain import Workflow, Node, Connection, new_workflow_id, new_node_id
# Phase 1 adds WorkflowExecutor — uncomment once it exists:
# from weftlyflow.engine.executor import WorkflowExecutor
# wf = Workflow(id=new_workflow_id(), project_id="pr_demo", name="demo", nodes=[...], connections=[...])
# result = await WorkflowExecutor().run(wf, initial_items=[])
# print(result.status)
print("Phase 1 scaffolding present.")
PY
```

### Phase 2 — Persistence + API

```bash
make lint && make typecheck && make test
make db-upgrade                    # applies migrations cleanly
pytest -m integration              # FastAPI + in-memory SQLite + fakeredis

# Smoke the HTTP surface:
make dev-api &                     # start server in background
sleep 2
curl -fsS http://localhost:5678/api/v1/docs >/dev/null   # OpenAPI UI reachable
curl -fsS http://localhost:5678/readyz
kill %1                            # stop server
```

### Phase 3 — Workers + webhooks + triggers

Needs Redis. Fastest path: `docker compose up -d redis`.

```bash
make lint && make typecheck && make test
pytest -m integration

# Run a worker against a real broker:
make dev-worker &
WORKER_PID=$!
sleep 2
# Post a webhook → expect a 202 and an execution row:
curl -fsS -X POST http://localhost:5678/webhook/demo -d '{"hello":"world"}' -H 'content-type: application/json'
kill "$WORKER_PID"
```

### Phase 4 — Expressions + credentials

```bash
make lint && make typecheck && make test
pytest tests/unit/expression -v
pytest tests/unit/credentials -v

# Manual expression smoke:
python - <<'PY'
# from weftlyflow.expression.resolver import resolve
# print(resolve("{{ $json.name }}", context={"$json": {"name": "weftlyflow"}}))
print("Phase 4 scaffolding present.")
PY
```

### Phase 5 — Frontend MVP

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run test
npm run build                      # emits dist/
npx playwright test                # golden-path E2E
```

### Phase 6+ — Integration nodes

Each new node ships with its own test folder. Validation:

```bash
make lint && make typecheck
pytest -m node tests/unit/nodes/<slug>
```

---

## 4. Housekeeping

```bash
make format        # ruff format + black + isort
make precommit     # run the full pre-commit matrix
make coverage      # HTML coverage report → htmlcov/index.html
make clean         # wipe caches + build artefacts
```

---

## 5. Troubleshooting

- **`make lint: ruff: No such file or directory`** — venv not activated.
  Run `source .venv/bin/activate`.
- **`ModuleNotFoundError: weftlyflow`** — run `pip install -e '.[dev,docs]'`.
- **Alembic fails with "no metadata"** — before Phase 2 this is expected:
  no entities are registered yet. `make db-upgrade` will become meaningful
  once Phase 2 lands.
- **Docker build hangs on apt-get** — check your corporate proxy; the base
  images pull from Debian mirrors.

---

## 6. Changing which commands exist

This file tracks what the phases claim. If you add or rename a `make` target,
update both `Makefile` and the matching row here in the same commit.
