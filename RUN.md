# RUN.md — how to run & validate Weftlyflow

This file is the single source of truth for:

1. **Bootstrapping** a fresh clone.
2. **Running** each subsystem locally.
3. **Validating** each phase delivered from `weftlyinfo.md §24`.

Every phase in the spec has a corresponding **validation block** below. When a
phase is claimed complete, run its block and confirm every command in it exits
with status `0`. If any step errors, the phase is **not** done.

Canonical design doc: [`weftlyinfo.md`](./weftlyinfo.md).

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

Live smoke — the spec's acceptance walk (login → create workflow → execute → read back):

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

No Redis is required for the test gate — the app boots with an
`InlineExecutionQueue` backed by `asyncio` tasks, and the trigger manager
uses an in-memory scheduler + leader lock. The production path (Celery +
Redis + APScheduler) is exercised by switching the queue/leader/scheduler
wiring in `weftlyflow.server.app.lifespan`, covered by unit tests over the
fakeredis-backed primitives.

```bash
make lint && make typecheck && make test
pytest -m integration              # Phase-2 and Phase-3 integration tests
pytest tests/unit/webhooks -v      # 23 webhook-layer unit tests
pytest tests/unit/triggers -v      # 22 trigger-layer unit tests (leader + scheduler + manager)
pytest tests/unit/worker   -v      # 12 worker/queue/idempotency unit tests
```

Live acceptance walk — hit a registered webhook and observe an execution:

```bash
# Terminal 1 — start the API (admin bootstrapped as in Phase 2).
WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL=admin@weftlyflow.io \
WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD=s3cret \
make dev-api

# Terminal 2 — create + activate a webhook-triggered workflow, then hit it.
BASE=http://localhost:5678
TOKEN=$(curl -sfS -X POST $BASE/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@weftlyflow.io","password":"s3cret"}' | jq -r .access_token)

WF=$(curl -sfS -X POST $BASE/api/v1/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d @- <<'JSON' | jq -r .id
{
  "name": "webhook-demo",
  "nodes": [
    {"id": "node_trigger", "name": "Webhook", "type": "weftlyflow.webhook_trigger",
     "parameters": {"path": "demo/hook", "method": "POST"}},
    {"id": "node_tag", "name": "Tag", "type": "weftlyflow.set",
     "parameters": {"assignments": [{"name": "tagged", "value": true}]}}
  ],
  "connections": [
    {"source_node": "node_trigger", "target_node": "node_tag"}
  ]
}
JSON
)

curl -sfS -X POST $BASE/api/v1/workflows/$WF/activate \
  -H "Authorization: Bearer $TOKEN"

RESP=$(curl -sfS -X POST $BASE/webhook/demo/hook \
  -H 'content-type: application/json' \
  -d '{"name":"world"}')
EX=$(echo "$RESP" | jq -r .execution_id)

# Worker finishes asynchronously; poll until status is terminal.
for _ in $(seq 1 20); do
  STATUS=$(curl -sfS $BASE/api/v1/executions/$EX -H "Authorization: Bearer $TOKEN" | jq -r .status)
  [ "$STATUS" = "success" ] && break
  sleep 0.2
done
echo "execution $EX status=$STATUS"

# Deactivate when done — the route should then 404 again.
curl -sfS -X POST $BASE/api/v1/workflows/$WF/deactivate \
  -H "Authorization: Bearer $TOKEN"
```

Production path with Celery + Redis (optional, out of the CI gate):

```bash
docker compose up -d redis
make dev-worker &
WORKER_PID=$!
# Same curl hits as above, but the `execute_workflow` task runs on the worker
# rather than in-process. Kill the worker when done:
kill "$WORKER_PID"
```

### Phase 4 — Expressions + credentials

No new services are required for the CI gate — the expression engine is
pure Python (RestrictedPython) and the credential cipher is an in-process
Fernet wrapper. Set `WEFTLYFLOW_ENCRYPTION_KEY` for a stable key in dev;
the lifespan will generate an ephemeral one when the env var is unset.

```bash
make lint && make typecheck && make test
pytest tests/unit/expression -v   # 26 tokenizer + resolver + proxy tests
pytest tests/unit/credentials -v  # 17 cipher + type tests
pytest tests/unit/nodes/test_http_request.py -v
pytest tests/integration/test_credentials.py -v
```

Manual expression smoke — demonstrates every proxy:

```bash
python - <<'PY'
from weftlyflow.expression import resolve, build_proxies
from weftlyflow.domain.execution import Item

proxies = build_proxies(
    item=Item(json={"name": "weftlyflow", "n": 3}),
    inputs=[Item(json={"name": "weftlyflow"})],
    workflow_id="wf_demo", workflow_name="demo", project_id="pr_demo",
    execution_id="ex_demo", execution_mode="manual",
    env_vars={"KEY": "v"},
)
print("single:", resolve("{{ $json.name }}", proxies))
print("mixed :", resolve("hello {{ $json.name }}!", proxies))
print("list  :", resolve("{{ [i*2 for i in range($json.n)] }}", proxies))
print("now   :", resolve("{{ $now.to_iso() }}", proxies))
PY
```

Live acceptance walk — HTTP Request node uses a stored credential + an
expression in its URL:

```bash
BASE=http://localhost:5678
WEFTLYFLOW_ENCRYPTION_KEY=$(python -c 'from weftlyflow.credentials import generate_key; print(generate_key())') \
WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL=admin@weftlyflow.io \
WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD=s3cret \
make dev-api &
API_PID=$!
sleep 1

TOKEN=$(curl -sfS -X POST $BASE/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@weftlyflow.io","password":"s3cret"}' | jq -r .access_token)

CRED=$(curl -sfS -X POST $BASE/api/v1/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"name":"demo","type":"weftlyflow.bearer_token","data":{"token":"demo-token"}}' \
  | jq -r .id)

WF=$(curl -sfS -X POST $BASE/api/v1/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d @- <<JSON | jq -r .id
{
  "name": "http-demo",
  "nodes": [
    {"id": "node_trigger", "name": "Trigger", "type": "weftlyflow.manual_trigger"},
    {"id": "node_http",    "name": "HTTP",    "type": "weftlyflow.http_request",
     "parameters": {"url": "https://httpbin.org/anything/{{ \$json.id }}", "method": "GET"},
     "credentials": {"auth": "$CRED"}}
  ],
  "connections": [{"source_node": "node_trigger", "target_node": "node_http"}]
}
JSON
)

curl -sfS -X POST $BASE/api/v1/workflows/$WF/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"initial_items":[{"id":42}]}' | jq '.status, .run_data.node_http[0].items[0][0].body.url, .run_data.node_http[0].items[0][0].body.headers.Authorization'

kill $API_PID
```

OAuth2 handshake (manual, when you have a real provider):

```bash
# 1. Pre-create an empty OAuth2 credential with provider URLs + client id/secret.
# 2. POST /api/v1/credentials/oauth2/authorize-url with { credential_id, redirect_uri }.
# 3. Open the returned authorize_url in a browser — sign in at the provider.
# 4. The provider redirects to GET /oauth2/callback?code=...&state=... which
#    exchanges the code for a token set and writes it back into the credential.
```

### Phase 5 — Frontend MVP

Vue 3 + Vite + TypeScript SPA under `/frontend`. The dev server proxies
`/api`, `/oauth2`, and `/webhook` to the backend at `:5678`.

One-time setup (per machine):

```bash
cd frontend
npm install
npx playwright install --with-deps chromium   # only needed for `npm run e2e`
```

Gate (runs without a backend; pure TS/build):

```bash
cd frontend
npm run typecheck                  # vue-tsc --noEmit
npm run test                       # vitest — unit smoke
npm run build                      # production bundle → dist/
```

Live dev — API + SPA side-by-side:

```bash
# Terminal 1 — backend (set the bootstrap admin once; SQLite file persists).
WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL=admin@weftlyflow.io \
WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD=s3cret \
make dev-api

# Terminal 2 — Vite dev server.
make dev-frontend                  # → http://localhost:5173
```

Sign in as `admin@weftlyflow.io` / `s3cret`. The editor lets you:

1. Create a workflow from the Home page.
2. Drag nodes from the palette onto the Vue Flow canvas, wire ports by
   dragging between handles, edit parameters + credentials in the right
   inspector.
3. Click Execute to run the workflow inline and inspect per-node run data
   in the bottom panel.
4. Activate / Deactivate a workflow to register its webhook + schedule
   triggers against the backend's trigger manager.
5. Manage credentials under the Credentials tab (`New credential` modal
   reads the type catalog and encrypts the payload server-side).

Golden-path Playwright E2E (needs backend running + `playwright install`):

```bash
cd frontend
WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL=admin@weftlyflow.io \
WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD=s3cret \
npm run e2e
```

The test logs in, creates a workflow, adds a Set node from the palette,
executes it, asserts the run panel shows status=success, then deletes
the workflow. It spins up Vite itself (`webServer` in
`playwright.config.ts`) but expects the backend to already be running
on `:5678`.

### Phase 6-core — Tier-1 node backfill

Adds the remaining Tier-1 MVP nodes (spec §25): `switch`, `filter`,
`merge`, `rename_keys`, `datetime_ops`, `evaluate_expression`,
`stop_and_error`, `execution_data`. The registry now ships **16
built-ins**.

Validation:

```bash
make lint && make typecheck && make test
pytest tests/unit/nodes/test_phase6_nodes.py -v    # 22 per-node unit tests
pytest tests/integration/test_phase6_nodes.py -v   # 2 integration chains
```

Quick smoke — run a chained workflow through the new nodes:

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

trig = Node(id=new_node_id(), name="Trigger", type="weftlyflow.manual_trigger")
flt = Node(
    id=new_node_id(), name="Adults", type="weftlyflow.filter",
    parameters={"field": "age", "operator": "greater_than_or_equal", "value": 18},
)
ev = Node(
    id=new_node_id(), name="Tag", type="weftlyflow.evaluate_expression",
    parameters={"expression": "{{ $json.name.upper() }}", "output_field": "display_name"},
)
sw = Node(
    id=new_node_id(), name="Route", type="weftlyflow.switch",
    parameters={
        "field": "country",
        "cases": [{"value": "US", "port": "case_1"}, {"value": "GB", "port": "case_2"}],
        "fallback_port": "default",
    },
)
us = Node(id=new_node_id(), name="US", type="weftlyflow.no_op")
gb = Node(id=new_node_id(), name="GB", type="weftlyflow.no_op")
other = Node(id=new_node_id(), name="Other", type="weftlyflow.no_op")

wf = Workflow(
    id=new_workflow_id(), project_id="pr_demo", name="demo",
    nodes=[trig, flt, ev, sw, us, gb, other],
    connections=[
        Connection(source_node=trig.id, target_node=flt.id),
        Connection(source_node=flt.id, target_node=ev.id),
        Connection(source_node=ev.id, target_node=sw.id),
        Connection(source_node=sw.id, target_node=us.id, source_port="case_1", source_index=0),
        Connection(source_node=sw.id, target_node=gb.id, source_port="case_2", source_index=1),
        Connection(source_node=sw.id, target_node=other.id, source_port="default", source_index=6),
    ],
)
items = [
    Item(json={"age": 10, "name": "Ada",    "country": "GB"}),
    Item(json={"age": 30, "name": "Grace",  "country": "US"}),
    Item(json={"age": 42, "name": "Edsger", "country": "NL"}),
]
execution = asyncio.run(WorkflowExecutor(registry).run(wf, initial_items=items))
print("status:", execution.status)
print("us     ->", [i.json["display_name"] for i in execution.run_data.per_node[us.id][0].items[0]])
print("other  ->", [i.json["display_name"] for i in execution.run_data.per_node[other.id][0].items[0]])
PY
```

Expected: `status: success`, `us` contains `['GRACE']`, `other` contains
`['EDSGER']` (Ada was filtered before reaching Switch).

### Phase 6+ — Integration nodes (Tier-2)

Tier-2 integrations still ship one PR at a time (see spec §25). Template:

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
