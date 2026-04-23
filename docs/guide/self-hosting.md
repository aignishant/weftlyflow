# Self-hosting

Weftlyflow is designed to be run by a small operations team on their own
infrastructure. The canonical deployment shape is three stateful
dependencies (Postgres, Redis, optional external secret store) plus three
stateless process classes (API, Celery worker, Celery beat).

This guide covers:

- [Deployment shapes](#deployment-shapes) — Docker Compose and Kubernetes
- [Required configuration](#required-configuration) — the four settings that must be changed from defaults
- [Scaling](#scaling) — which processes are horizontal-safe and which are singletons
- [Backups and key rotation](#backups-and-key-rotation) — Postgres + Fernet encryption key
- [Observability](#observability) — probes, metrics, structured logs
- [Production checklist](#production-checklist)

## Deployment shapes

### Docker Compose (small / single-host)

`docker-compose.yml` at the repo root brings up the full stack:

```bash
cp .env.example .env
# Edit .env — at minimum set WEFTLYFLOW_SECRET_KEY and
# WEFTLYFLOW_ENCRYPTION_KEY (see "Required configuration" below).
docker compose up -d
```

The compose file declares:

| Service    | Image / build                              | Purpose                                    |
| ---------- | ------------------------------------------ | ------------------------------------------ |
| `postgres` | `postgres:16-alpine`                       | Primary store                              |
| `redis`    | `redis:7-alpine`                           | Celery broker + nonce store + queue state  |
| `api`      | `docker/api.Dockerfile`                    | FastAPI on `:5678`                         |
| `worker`   | `docker/worker.Dockerfile` × 2             | Celery task executors                      |
| `beat`     | `docker/beat.Dockerfile`                   | Celery beat singleton (cron + retention)   |

Worker replicas scale through the compose `deploy.replicas` key or a
`docker compose up --scale worker=N` override.

### Kubernetes (Helm)

A first-party chart lives at `deploy/helm/weftlyflow/`. It ships API,
worker, and beat Deployments plus a migration Job, ConfigMap/Secret,
Service, Ingress, NetworkPolicy, PDB, HPA, and a ServiceAccount. Bitnami
Postgres and Redis are optional conditional sub-charts.

```bash
helm dependency update deploy/helm/weftlyflow
helm install weftlyflow deploy/helm/weftlyflow \
  --namespace weftlyflow --create-namespace \
  --set config.secretKey=<generated> \
  --set config.encryptionKey=<generated>
```

Point at external Postgres / Redis by setting `postgresql.enabled=false`
and supplying `externalDatabase.url`, or the Redis equivalent.

### Single-binary dev

`make install && make dev-api` runs the API against a local SQLite file
with inline execution (no Redis or Celery). Suitable for local
experimentation only — migrations, queueing, and leader election all
behave differently in the compose / k8s shape.

## Required configuration

Four settings have defaults that **must** be overridden before the first
production start. A misconfigured install either refuses to boot or
silently runs in an insecure shape.

| Setting                         | Default                   | What happens if you leave it                           |
| ------------------------------- | ------------------------- | ------------------------------------------------------ |
| `WEFTLYFLOW_SECRET_KEY`         | `change-me`               | JWTs signed with `change-me` — anyone can forge tokens |
| `WEFTLYFLOW_ENCRYPTION_KEY`     | *(empty)*                 | Credentials encrypted with an ephemeral key, lost on restart |
| `WEFTLYFLOW_DATABASE_URL`       | `sqlite+aiosqlite://…`    | SQLite is fine for dev, never for production           |
| `WEFTLYFLOW_REDIS_URL`          | `redis://localhost:6379/0`| Celery cannot queue across workers                     |

Generate a Fernet key with:

```bash
python -c "from weftlyflow.credentials.cipher import generate_key; print(generate_key())"
```

`SECRET_KEY` can be any high-entropy string; `python -c "import secrets;
print(secrets.token_urlsafe(64))"` is the canonical source.

## Scaling

| Process  | Horizontal-safe? | Notes                                                                                     |
| -------- | ---------------- | ----------------------------------------------------------------------------------------- |
| API      | **Yes**          | Each pod is stateless. See the nonce-store caveat below for SSO.                          |
| Worker   | **Yes**          | Celery distributes tasks through Redis. Soft + hard time-limits are per-task.             |
| Beat     | **No (singleton)** | Exactly one beat pod — it's the cron source of truth. The Helm chart pins `replicas: 1`. |
| Triggers | **Leader only**  | Webhook + cron triggers only fire on the leader API pod; others proxy through the DB.     |

### SSO nonce store under horizontal scaling

`sso_nonce_store_backend` defaults to `memory`, which is process-local.
When running more than one API pod, flip it to `redis`:

```bash
WEFTLYFLOW_SSO_NONCE_STORE_BACKEND=redis
```

Otherwise a captured SSO callback URL can be replayed against a pod that
didn't see the original login. See the
[SSO guide](single-sign-on.md#replay-protection) for the full rationale.

### Worker concurrency

Celery worker concurrency defaults to the CPU count. Set
`--concurrency=N` in the worker command, or size via the Helm chart's
`worker.concurrency` value. Right-size by queue depth, not CPU — most
Weftlyflow nodes are I/O-bound.

## Backups and key rotation

### Postgres

`pg_dump` against the `weftlyflow` database is sufficient. The schema is
self-contained; there are no cross-database references. Retain dumps
at least as long as `audit_retention_days` (default 90) so a restore
doesn't lose the audit trail you were relying on.

### Encryption key rotation

Credentials are encrypted at rest with `ENCRYPTION_KEY` (Fernet).
Rotating the key is online-safe because the decryption path tries every
key in a ring:

1. Generate a new key.
2. Move the current key into `WEFTLYFLOW_ENCRYPTION_KEY_OLD_KEYS`
   (comma-separated if you already had old entries) and set
   `WEFTLYFLOW_ENCRYPTION_KEY` to the new key.
3. Roll the API pods. New writes use the new key; existing ciphertexts
   still decrypt against the old key.
4. After every credential has been resaved (happens organically as
   workflows use them, or forcibly by re-saving each credential through
   the UI / CLI), drop the retired key from `ENCRYPTION_KEY_OLD_KEYS`.

Keep at least one old key in the ring until you're certain no
`encryption_key_version=<old>` row remains — losing the only key that
decrypts a row makes that credential permanently unrecoverable.

## Observability

### Health probes

| Endpoint   | Probe kind   | Returns                                                       |
| ---------- | ------------ | ------------------------------------------------------------- |
| `/healthz` | liveness     | 200 while the process is up. Fast, no I/O.                    |
| `/readyz`  | readiness    | 200 when the DB is reachable and the node registry is warm.   |

The Helm chart wires both into the API Deployment.

### Prometheus metrics

`GET /metrics` exposes request, execution, queue, and sandbox counters
and histograms. Disabled with `WEFTLYFLOW_METRICS_ENABLED=false` when
the surface is undesirable.

Scrape with a `ServiceMonitor` or Prometheus job:

```yaml
scrape_configs:
  - job_name: weftlyflow
    metrics_path: /metrics
    static_configs:
      - targets: ["weftlyflow-api:5678"]
```

### Logs

`WEFTLYFLOW_LOG_FORMAT=json` in production. Every line is a single JSON
document with `event`, `timestamp`, plus bound context
(`execution_id`, `node_id`, `user_id` where applicable). Pipe to any
JSON-aware aggregator.

## Production checklist

Run through this before the first user traffic lands on the deployment.

- [ ] `WEFTLYFLOW_SECRET_KEY` and `WEFTLYFLOW_ENCRYPTION_KEY` set to
      high-entropy values, stored in the orchestrator's secret store
      (never in the image).
- [ ] `WEFTLYFLOW_DATABASE_URL` points at a managed Postgres with
      point-in-time recovery or a backup cadence you've tested.
- [ ] `WEFTLYFLOW_PUBLIC_URL` set to the externally reachable URL —
      every OAuth / SSO / webhook callback uses it.
- [ ] `WEFTLYFLOW_CORS_ORIGINS` locked down to your frontend origin.
      The default of `http://localhost:5173` is a dev convenience.
- [ ] TLS terminated at the ingress / load balancer.
- [ ] `WEFTLYFLOW_LOG_FORMAT=json` for aggregation.
- [ ] `WEFTLYFLOW_REGISTRATION_ENABLED=false` unless self-serve signup
      is genuinely the intended policy.
- [ ] If running multi-instance: `WEFTLYFLOW_SSO_NONCE_STORE_BACKEND=redis`.
- [ ] If the Code node is enabled: review the sandbox limits
      (`code_node_cpu_seconds`, `code_node_memory_bytes`,
      `code_node_wall_clock_seconds`) against the workload.
- [ ] Metrics endpoint scraped; dashboards or alerts watching
      `weftlyflow_execution_failed_total`.
- [ ] Backup restore rehearsed at least once against a scratch
      environment.
