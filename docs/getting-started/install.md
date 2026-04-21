# Install

## Option A — Docker (recommended)

```bash
git clone <weftlyflow-repo> ng8
cd ng8
cp .env.example .env
# Generate an encryption key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste into WEFTLYFLOW_ENCRYPTION_KEY in .env
make docker-up
```

Services:

- API: http://localhost:5678
- Docs: http://localhost:8000 (after `make docs-serve`)
- Frontend dev: http://localhost:5173 (after `make dev-frontend`)

## Option B — Local Python

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs,ai]"
pre-commit install

cp .env.example .env
# Set WEFTLYFLOW_ENCRYPTION_KEY as above.

# Start services you need
docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=weftlyflow -e POSTGRES_USER=weftlyflow -e POSTGRES_DB=weftlyflow postgres:16-alpine &
docker run --rm -p 6379:6379 redis:7-alpine &

make db-upgrade
make dev-api       # :5678
# in separate shells:
make dev-worker
make dev-beat
```

## Verify

```bash
curl http://localhost:5678/healthz
# {"status":"ok","version":"0.1.0a0"}
```

## Troubleshooting

- **`WEFTLYFLOW_ENCRYPTION_KEY` missing** → credentials can't be encrypted. Generate one (see above) and set it in `.env`.
- **Alembic can't find migrations** → run from the repo root; `alembic.ini` points to `src/weftlyflow/db/migrations`.
- **Celery worker won't start** → Redis isn't reachable; check `WEFTLYFLOW_CELERY_BROKER_URL`.
