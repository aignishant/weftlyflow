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
pytest tests/unit/engine -v        # 22 engine-layer unit tests
pytest tests/unit/nodes  -v        # 46 node-layer unit tests
pytest tests/unit/test_smoke.py    # Phase-0 smoke still passes
```

Live smoke — runs the 5-node acceptance workflow end to end:

```bash
python - <<'PY'
import asyncio
from weftlyflow.domain.execution import Item
from weftlyflow.domain.ids import new_node_id, new_workflow_id
from weftlyflow.domain.workflow import Connection, Node, Workflow
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.nodes.registry import NodeRegistry

registry = NodeRegistry()
registry.load_builtins()
print(f"registered {len(registry)} builtin nodes")

trigger = Node(id=new_node_id(), name="Trigger", type="weftlyflow.manual_trigger")
setter = Node(id=new_node_id(), name="Tag", type="weftlyflow.set",
              parameters={"assignments": [{"name": "tagged", "value": True}]})
decision = Node(id=new_node_id(), name="Adult?", type="weftlyflow.if",
                parameters={"field": "age", "operator": "greater_than_or_equal", "value": 18})
adults = Node(id=new_node_id(), name="Adults", type="weftlyflow.no_op")
minors = Node(id=new_node_id(), name="Minors", type="weftlyflow.code")

wf = Workflow(
    id=new_workflow_id(), project_id="pr_demo", name="demo",
    nodes=[trigger, setter, decision, adults, minors],
    connections=[
        Connection(source_node=trigger.id, target_node=setter.id),
        Connection(source_node=setter.id, target_node=decision.id),
        Connection(source_node=decision.id, target_node=adults.id,
                   source_port="true", source_index=0),
        Connection(source_node=decision.id, target_node=minors.id,
                   source_port="false", source_index=1),
    ],
)
items = [Item(json={"age": 30}), Item(json={"age": 10}), Item(json={"age": 21})]
execution = asyncio.run(WorkflowExecutor(registry).run(wf, initial_items=items))

print(f"status: {execution.status}")
print(f"adults -> {[i.json for i in execution.run_data.per_node[adults.id][0].items[0]]}")
print(f"minors -> {[i.json for i in execution.run_data.per_node[minors.id][0].items[0]]}")
PY
```

Expected output: `status: success`, adults list contains ages 30 and 21
(both tagged), minors contains age 10 (also tagged).

### Phase 2 — Persistence + API

```bash
make lint && make typecheck && make test
pytest -m integration              # 21 HTTP + DB integration tests
```

Live smoke — the bible's acceptance walk (login → create workflow → execute → read back):

```bash
# Terminal 1 — start the server. First boot auto-creates an admin; the
# generated password prints at warning level in the log. Or pre-seed it:
WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL=admin@weftlyflow.io \
WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD=s3cret \
make dev-api

# Terminal 2 — exercise the API:
BASE=http://localhost:5678
TOKEN=$(curl -sfS -X POST $BASE/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@weftlyflow.io","password":"s3cret"}' | jq -r .access_token)

WF=$(curl -sfS -X POST $BASE/api/v1/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d @- <<'JSON' | jq -r .id
{
  "name": "acceptance",
  "nodes": [
    {"id": "trigger", "name": "Trigger", "type": "weftlyflow.manual_trigger"},
    {"id": "tag", "name": "Tag", "type": "weftlyflow.set",
     "parameters": {"assignments": [{"name": "tagged", "value": true}]}},
    {"id": "decide", "name": "Adult?", "type": "weftlyflow.if",
     "parameters": {"field": "age", "operator": "greater_than_or_equal", "value": 18}},
    {"id": "adults", "name": "Adults", "type": "weftlyflow.no_op"},
    {"id": "minors", "name": "Minors", "type": "weftlyflow.code"}
  ],
  "connections": [
    {"source_node": "trigger", "target_node": "tag"},
    {"source_node": "tag", "target_node": "decide"},
    {"source_node": "decide", "target_node": "adults", "source_port": "true",  "source_index": 0},
    {"source_node": "decide", "target_node": "minors", "source_port": "false", "source_index": 1}
  ]
}
JSON
)

EX=$(curl -sfS -X POST $BASE/api/v1/workflows/$WF/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"initial_items":[{"age":30},{"age":10},{"age":21}]}' | jq -r .id)

curl -sfS $BASE/api/v1/executions/$EX -H "Authorization: Bearer $TOKEN" | jq .status
# -> "success"
```

Other useful Phase-2 endpoints:

```bash
curl -sfS $BASE/api/v1/node-types -H "Authorization: Bearer $TOKEN" | jq '. | length'
curl -sfS $BASE/api/v1/workflows  -H "Authorization: Bearer $TOKEN"
curl -sfS $BASE/api/v1/executions -H "Authorization: Bearer $TOKEN"
curl -sfS $BASE/readyz                      # 200 ready; 503 if DB is down
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
