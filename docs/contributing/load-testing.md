# Load testing

Two tiers of load testing ship with the repo.

## Tier 1 — in-process wall-clock probes

`tests/load/test_engine_throughput.py` contains pytest-marked `load`
cases that run inside the test process, with no network, no DB, no
Celery. They exercise the hottest internal paths — expression eval,
engine step — and assert a *loose* wall-clock budget.

```bash
make test-load
```

Budgets are sized to catch an order-of-magnitude regression, not a 5%
one. Raise them when legitimate; do not chase flakes.

## Tier 2 — Locust against a running stack

`tests/load/locustfile.py` drives the public API from outside the
process using [Locust](https://locust.io). This is the tier to use
for deployment-sizing questions or for finding bottlenecks that only
show up end-to-end (Postgres connection pool, Redis round-trip
latency, JSON serialisation at the boundary).

### Setup

```bash
# 1. Install the load extra:
pip install -e ".[load]"

# 2. Bring up the stack (or point at any running deployment):
make docker-up

# 3. Seed a bootstrap admin. The compose stack creates one on
#    first boot — override via env vars if you set different
#    credentials.
export WEFTLYFLOW_LOADGEN_EMAIL=admin@example.com
export WEFTLYFLOW_LOADGEN_PASSWORD=change-me

# 4. Open the Locust UI:
make loadgen

# → http://localhost:8089
```

### Scenarios included

| Task | Weight | What it exercises |
|------|-------:|-------------------|
| `health` | 10 | Uvicorn + routing baseline |
| `list_workflows` | 3 | Auth + DB read |
| `me` | 1 | Auth + user fetch |

Extend the file as you chase a specific question — adding scenarios
like `trigger_execution` or `webhook_ingest` is a one-method change.

### What to measure

- **p95 latency** per scenario under your deployment's target
  concurrency.
- **Error rate** — should stay at 0% under reasonable load; any
  non-zero is a bug, not a capacity limit.
- **Queue depth** in the Celery worker (from Prometheus, if you
  scrape `/metrics`) while the load generator is running — that's
  where execution-path bottlenecks surface.

### What *not* to do

- Do not run Locust against a shared / production instance without
  the owner's explicit say-so. Even at modest concurrency, Locust is
  a denial-of-service tool if pointed at something it shouldn't
  be.
- Do not commit results to the repo. They are environment-specific;
  treat them like benchmark printouts.
