.PHONY: help install dev-api dev-worker dev-beat dev-frontend \
        lint format typecheck test test-unit test-integration test-node coverage \
        docs-serve docs-build docs-gen \
        db-upgrade db-downgrade db-revision db-reset \
        docker-build docker-up docker-down \
        precommit clean

help:
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------- setup ----------
install: ## Install package + dev + docs extras (editable)
	pip install -e ".[dev,docs,ai]"
	pre-commit install

# ---------- run locally ----------
dev-api: ## Run API server with reload (http://localhost:5678)
	uvicorn weftlyflow.server.app:app --reload --host 0.0.0.0 --port 5678 --log-level debug

dev-worker: ## Run a Celery worker
	celery -A weftlyflow.worker.app worker -l info -Q executions,polling,io,priority -c 4

dev-beat: ## Run Celery Beat (single instance!)
	celery -A weftlyflow.worker.app beat -l info

dev-frontend: ## Run Vite dev server (http://localhost:5173)
	cd frontend && npm run dev

# ---------- lint / format / type ----------
lint: ## ruff check
	ruff check src tests

format: ## ruff format + black + isort
	ruff format src tests
	black src tests
	isort src tests

typecheck: ## mypy --strict
	mypy src/weftlyflow

# ---------- tests ----------
test: test-unit ## Alias for test-unit

test-unit: ## Fast unit tests
	pytest -m "unit or not integration and not node and not live and not load"

test-integration: ## Integration tests (needs Redis + SQLite)
	pytest -m integration

test-node: ## Per-node tests
	pytest -m node

test-all: ## Everything except live/load
	pytest -m "not live and not load"

coverage: ## Coverage report
	pytest --cov=weftlyflow --cov-report=term-missing --cov-report=html

# ---------- docs ----------
docs-gen: ## Regenerate API reference pages
	python scripts/gen_ref_pages.py

docs-serve: ## Live-reload docs site (http://localhost:8000)
	DISABLE_MKDOCS_2_WARNING=true mkdocs serve

docs-build: ## Build static site into ./site/
	DISABLE_MKDOCS_2_WARNING=true mkdocs build --strict

# ---------- db ----------
db-upgrade: ## Apply all migrations
	alembic upgrade head

db-downgrade: ## Roll back one migration
	alembic downgrade -1

db-revision: ## New migration (MSG="...")
	alembic revision --autogenerate -m "$(MSG)"

db-reset: ## DESTROY and recreate the dev DB
	@read -p "This wipes the dev DB. Type 'yes' to continue: " ok && [ "$$ok" = "yes" ]
	alembic downgrade base
	alembic upgrade head

# ---------- docker ----------
docker-build: ## Build all service images
	docker compose build

docker-up: ## Start full stack (api + worker + beat + redis + postgres)
	docker compose up -d

docker-down: ## Stop the stack
	docker compose down

# ---------- misc ----------
precommit: ## Run pre-commit on all files
	pre-commit run --all-files

clean: ## Remove caches and build artefacts
	rm -rf build/ dist/ .pytest_cache .mypy_cache .ruff_cache htmlcov/ site/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
