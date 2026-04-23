# Weftlyflow Helm Chart

Chart version `0.1.0` / App version `0.1.0a0`.

Deploys the full Weftlyflow stack to Kubernetes:

- **api** — FastAPI application + webhook ingress (port 5678)
- **worker** — Celery worker (queues: executions, polling, io, priority)
- **beat** — Celery Beat scheduler (singleton, replicas hard-coded to 1)
- **migration Job** — runs `alembic upgrade head` as a pre-install/pre-upgrade hook
- Optional **PostgreSQL** and **Redis** via Bitnami sub-charts

## Prerequisites

- Kubernetes 1.25+
- Helm 3.12+
- `metrics-server` installed if HPA is enabled
- A CNI that honours `NetworkPolicy` if `networkPolicy.enabled: true`

## Quick start (turnkey — sub-charts included)

```bash
# 1. Fetch sub-chart dependencies (required once, and after Chart.yaml changes)
helm dependency update deploy/helm/weftlyflow

# 2. Install with a minimal secret override
helm install weftlyflow deploy/helm/weftlyflow \
  --namespace weftlyflow \
  --create-namespace \
  --set secrets.jwtSecretKey="$(openssl rand -hex 32)" \
  --set secrets.encryptionKey="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

## Production install (external DB and Redis)

```bash
helm install weftlyflow deploy/helm/weftlyflow \
  --namespace weftlyflow \
  --create-namespace \
  --set postgresql.enabled=false \
  --set redis.enabled=false \
  --set externalDatabase.url="postgresql+psycopg://user:pass@mydb:5432/weftlyflow" \
  --set externalRedis.url="redis://:password@myredis:6379/0" \
  --set secrets.jwtSecretKey="<your-key>" \
  --set secrets.encryptionKey="<your-fernet-key>"
```

## Using a pre-existing Secret

Create your secret before installing:

```bash
kubectl create secret generic weftlyflow-credentials \
  --from-literal=WEFTLYFLOW_JWT_SECRET_KEY="..." \
  --from-literal=WEFTLYFLOW_ENCRYPTION_KEY="..." \
  --from-literal=WEFTLYFLOW_DATABASE_URL="..." \
  --from-literal=WEFTLYFLOW_REDIS_URL="..." \
  --from-literal=WEFTLYFLOW_CELERY_BROKER_URL="..." \
  --from-literal=WEFTLYFLOW_CELERY_RESULT_BACKEND="..."
```

Then install with:

```bash
helm install weftlyflow deploy/helm/weftlyflow \
  --set existingSecret=weftlyflow-credentials \
  ...
```

## Upgrade

```bash
helm upgrade weftlyflow deploy/helm/weftlyflow \
  --namespace weftlyflow \
  --reuse-values
```

The migration Job runs automatically as a pre-upgrade hook before the new
Deployments are applied.

## Uninstall

```bash
helm uninstall weftlyflow --namespace weftlyflow
# PVCs created by sub-charts are NOT deleted automatically.
kubectl delete pvc -l app.kubernetes.io/instance=weftlyflow -n weftlyflow
```

## Configure values

The three Deployment templates and their knobs:

| Template | Key section in `values.yaml` |
|---|---|
| `templates/api-deployment.yaml` | `api.*`, `image.*`, `config.*`, `secrets.*`, `extraEnv`, `extraEnvFrom` |
| `templates/worker-deployment.yaml` | `worker.*`, same shared env keys |
| `templates/beat-deployment.yaml` | `beat.*`, same shared env keys |

All three Deployments receive the same `ConfigMap` and `Secret` via `envFrom`.
Use `extraEnv` (list of `{name, value}`) to inject additional `WEFTLYFLOW_*`
settings without modifying `config`. Use `extraEnvFrom` to mount additional
`ConfigMapRef` or `SecretRef` sources wholesale.

### Key operational knobs

| Value | Default | Notes |
|---|---|---|
| `api.replicaCount` | 2 | Scale up for traffic; pairs with `hpa.api` |
| `worker.replicaCount` | 2 | Scale up for throughput; pairs with `hpa.worker` |
| `beat` replicas | **1 (hard-coded)** | Never change — leader election constraint |
| `ingress.enabled` | false | Enable and set `ingress.hosts` to expose externally |
| `networkPolicy.enabled` | false | Requires a NetworkPolicy-aware CNI |
| `hpa.api.enabled` | false | Requires metrics-server |
| `hpa.worker.enabled` | false | Requires metrics-server |
| `pdb.api.enabled` | true | Protects against mass eviction during drains |
| `migrationJob.enabled` | true | Disable only if you run migrations out-of-band |
| `postgresql.enabled` | true | Disable and set `externalDatabase.url` for external DB |
| `redis.enabled` | true | Disable and set `externalRedis.url` for external Redis |

## Image naming convention

Images are resolved as:
```
<image.registry>/<image.repositoryPrefix>/<component>:<tag>
```
Default: `ghcr.io/weftlyflow/weftlyflow/api:0.1.0a0`

Override `image.tag` to pin a specific release or use `image.registry` /
`image.repositoryPrefix` to point at a private registry.
