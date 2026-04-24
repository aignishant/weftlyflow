<div align="center">

<img src="./docs/images/dashboard.png" alt="Weftlyflow dashboard" width="100%" />

# Weftlyflow

**Self-hosted workflow automation — visual node-graph editor, triggers, AI agents, and 100+ integrations.**

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue-3-42b883?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Postgres](https://img.shields.io/badge/Postgres-15+-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-success)](./weftlyinfo.md)

[**Quickstart**](#-quickstart) ·
[**Features**](#-whats-in-the-box) ·
[**Stack**](#-stack) ·
[**Docs**](#-documentation) ·
[**Architecture**](#-architecture) ·
[**Contributing**](#-contributing)

</div>

---

> Weftlyflow is an **independent, clean-room Python implementation** inspired by n8n's architecture.
> The canonical project plan lives in [`weftlyinfo.md`](./weftlyinfo.md) — treat it as the source of truth for design and contribution rules.

## ✨ Highlights

<table>
<tr>
<td width="33%" valign="top">

### 🧩 Visual editor
Drag-and-drop node graph with searchable palette, live expression hints, parameter inspector, and one-click execution.

</td>
<td width="33%" valign="top">

### ⚡ Production-grade engine
Async core, RestrictedPython sandbox for Code nodes, subprocess isolation, expression timeouts, and PII redaction baked in.

</td>
<td width="33%" valign="top">

### 🤖 AI-native
First-class agents, memory, vector stores, embeddings, and guardrails — works with OpenAI, Anthropic, Cohere, or any local OpenAI-compatible model.

</td>
</tr>
<tr>
<td width="33%" valign="top">

### 🔐 Enterprise auth
Argon2 + JWT, RBAC, optional TOTP, OIDC + SAML SSO, and external-secrets protocol (AWS Secrets Manager out of the box).

</td>
<td width="33%" valign="top">

### 📦 100+ integrations
Slack, GitHub, Jira, Notion, Stripe, Salesforce, HubSpot, Google Sheets, AWS, Postgres, Mongo… all encrypted-credential aware.

</td>
<td width="33%" valign="top">

### 🛠 Self-hosted, no lock-in
Docker compose, Postgres + Redis, Helm-friendly, structlog + Prometheus + OTel observability, audit retention.

</td>
</tr>
</table>

---

## 📸 Screenshots

<div align="center">

### Dashboard

Workflow list, live KPIs, pre-built templates, integration gallery, quick actions.

<img src="./docs/images/dashboard.png" alt="Dashboard" width="90%" />

### Workflow editor

Three-pane editor — searchable node palette (127 nodes across triggers / core / integrations / AI), Vue Flow canvas, and parameter inspector with live expression hints.

<img src="./docs/images/workflow-editor.png" alt="Workflow editor" width="90%" />

</div>

---

## 📊 Status

**Version `1.0.0`.** Phases 0–5 complete; phase 6 (integration nodes) is the active expansion track; phase 7 (AI) ships a working baseline; phase 8 hardening (sandbox, SSO, external-secrets, audit retention, fuzz suite) is complete.

| Phase | Scope | State |
|---|---|:---:|
| **0** | Repo bootstrap, tooling, IP/clean-room rules | ✅ |
| **1** | Domain model, execution engine, expression sandbox | ✅ |
| **2** | Persistence, FastAPI surface, auth, RBAC | ✅ |
| **3** | Worker, webhook ingress, scheduler, triggers | ✅ |
| **4** | Credentials vault (Fernet), expression engine v2 | ✅ |
| **5** | Frontend MVP (editor, executions, credentials) | ✅ |
| **6** | Integration nodes — 85+ shipped, more landing | 🚧 |
| **7** | AI nodes — agents, memory, vector stores, guardrails | ✅ baseline |
| **8a** | Sandbox hardening, expression timeouts, redaction | ✅ |
| **8b** | Subprocess runner, fuzz suite, SSO, external secrets, audit retention | ✅ |

---

## 📦 What's in the box

<table align="center">
<tr>
  <th align="center">Built-in nodes</th>
  <th align="center">Credentials</th>
  <th align="center">Templates</th>
  <th align="center">Backend tests</th>
  <th align="center">Phases delivered</th>
</tr>
<tr>
  <td align="center"><strong>127</strong><br/><sub>4 triggers · 21 core<br/>85 integrations · 17+ AI</sub></td>
  <td align="center"><strong>89</strong><br/><sub>encrypted via Fernet</sub></td>
  <td align="center"><strong>22</strong><br/><sub>one-click installs</sub></td>
  <td align="center"><strong>172</strong><br/><sub>files in unit/, integration/</sub></td>
  <td align="center"><strong>0–5 + 8a + 8b</strong><br/><sub>plus AI baseline</sub></td>
</tr>
</table>

<details>
<summary><strong>🟢 Triggers (4)</strong></summary>

`weftlyflow.manual_trigger` · `weftlyflow.schedule_trigger` (cron / interval) · `weftlyflow.webhook_trigger` · `weftlyflow.trigger_chat`

</details>

<details>
<summary><strong>🧩 Core nodes (21)</strong></summary>

| Group | Nodes |
|---|---|
| **Routing & flow** | `if`, `switch`, `merge`, `filter`, `split_in_batches`, `wait`, `no_op`, `stop_and_error` |
| **Data shaping** | `set`, `rename_keys`, `transform`, `evaluate_expression`, `compare_datasets` |
| **HTTP & code** | `http_request`, `code` (RestrictedPython sandbox), `function_call` |
| **Parsing & files** | `html_parse`, `xml_parse`, `datetime_ops`, `read_binary_file`, `write_binary_file`, `execution_data` |

</details>

<details>
<summary><strong>🔌 Integrations (85+)</strong></summary>

| Category | Services |
|---|---|
| **Communication** | Slack · Discord · Telegram · MS Teams · Twilio · SendGrid · Mailgun · SMTP · IMAP |
| **Engineering** | GitHub · GitLab · Bitbucket · Jira · Linear · PagerDuty · Sentry |
| **Productivity** | Notion · Asana · ClickUp · Trello · Monday · Airtable · Google Sheets · Google Drive · Gmail · Box · Dropbox |
| **Sales / CRM** | Salesforce · HubSpot · Pipedrive · Intercom · Zendesk · Zoho · Mailchimp |
| **Commerce / payments** | Stripe · Shopify · QuickBooks · Square |
| **Cloud / data** | AWS S3 · DynamoDB · Postgres · MySQL · MongoDB · Redis |
| **…and ~40 more** | see the in-app node palette |

</details>

<details>
<summary><strong>🤖 AI nodes (17+)</strong></summary>

| Group | Nodes |
|---|---|
| **LLM providers** | OpenAI · Anthropic · Cohere · local OpenAI-compatible |
| **Agents & memory** | `agent_react`, `agent_tool_dispatch`, `agent_tool_result`, `memory_buffer`, `memory_window`, `memory_summary` |
| **Retrieval** | `embed_openai`, `embed_local`, `text_splitter`, `vector_chroma`, `vector_pgvector`, `vector_pinecone`, `vector_qdrant`, `vector_memory` |
| **Guardrails** | `guard_jailbreak_detect`, `guard_pii_redact`, `guard_schema_enforce` |
| **Conversational** | `trigger_chat`, `chat_respond` |

</details>

---

## 🧱 Stack

<table>
<tr>
<td valign="top" width="50%">

#### Backend
- **Python 3.12** (3.11 supported)
- **FastAPI** + **SQLAlchemy 2** + **Alembic**
- **Pydantic v2**
- **Celery** + **Redis** + **APScheduler**
- **RestrictedPython** sandbox
- **structlog** · **httpx**
- **`cryptography`** (Fernet at-rest encryption)

</td>
<td valign="top" width="50%">

#### Frontend
- **Vue 3** Composition API
- **Pinia** · **Vue Router** · **Vue Flow**
- **CodeMirror 6**
- **Tailwind v4** · **Vite** · **TypeScript 5**

</td>
</tr>
<tr>
<td valign="top" width="50%">

#### Tooling
- `pip` + `hatch` (PEP 621)
- `ruff` · `black` · `mypy --strict`
- `pytest` (+ `respx`, `hypothesis`, `xdist`)
- `Playwright` for E2E
- `pre-commit`
- `mkdocs-material` + `mkdocstrings`

</td>
<td valign="top" width="50%">

#### Infra & security
- Docker + docker-compose
- Postgres (prod) / SQLite (dev) / Redis
- **Argon2** + **JWT** · **RBAC** · optional **TOTP**
- **OIDC** + **SAML** SSO
- External-secrets protocol (AWS Secrets Manager built in)

</td>
</tr>
</table>

---

## 🚀 Quickstart

### Docker (recommended)

```bash
cp .env.example .env
docker compose up -d                     # postgres, redis, api, worker, beat
docker compose exec api alembic upgrade head
cd frontend && npm install && npm run dev   # UI on http://localhost:5173
```

API on `http://localhost:5678` (`/healthz`, `/api/v1/...`). Default bootstrap admin
is generated on first boot (password printed once, redacted on subsequent logs).
Pre-seed deterministically with `WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL` and
`WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD` in `.env`.

### Native dev (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs,ai]"
cp .env.example .env
make db-upgrade
make dev-api        # http://localhost:5678
make dev-worker     # separate shell
make dev-beat       # separate shell
make dev-frontend   # http://localhost:5173
make docs-serve     # http://localhost:8000 (optional)
```

The local CI gate is:

```bash
make lint && make typecheck && make test
```

### 📷 Capturing fresh screenshots

After running the stack:

```bash
cd frontend && node scripts/capture_screenshots.mjs
```

Outputs `docs/images/dashboard.png` and `docs/images/workflow-editor.png`.

---

## 🏗 Architecture

```text
                  ┌──────────────────────────────────────────────────┐
                  │                Vue 3 + Vite frontend             │
                  │  editor · executions · credentials · settings    │
                  └────────────────────────┬─────────────────────────┘
                                           │ REST / SSE
                  ┌────────────────────────▼─────────────────────────┐
                  │                   FastAPI server                 │
                  │  routers · auth (JWT/SSO) · RBAC · webhooks      │
                  └─┬──────────────┬───────────────┬─────────────────┘
                    │              │               │
        ┌───────────▼───┐  ┌───────▼──────┐  ┌─────▼────────┐
        │   engine      │  │  triggers    │  │   worker     │
        │ DAG scheduler │  │ cron / poll  │  │  Celery      │
        │ async runtime │  │ APScheduler  │  │  + sandbox   │
        └─┬──────┬──────┘  └──────────────┘  └──────────────┘
          │      │
   ┌──────▼──┐ ┌─▼──────────┐ ┌──────────────┐ ┌──────────────┐
   │  nodes  │ │ expression │ │ credentials  │ │   domain     │
   │ 127 BIs │ │  sandbox   │ │ Fernet vault │ │ pure types   │
   └─────────┘ └────────────┘ └──────────────┘ └──────────────┘
```

**Layer rule (no back-edges):** `server / worker / webhooks / triggers → engine → nodes / credentials / expression → domain`

```
src/weftlyflow/        backend Python package (domain, engine, nodes, server, worker, …)
frontend/              Vue 3 + Vite + TS app
docs/                  mkdocs source + screenshots
tests/                 backend tests (unit/, integration/)
docker/                Dockerfiles per service (api, worker, beat)
alembic/               DB migrations (handled by `make db-upgrade`)
.claude/               Claude Code config (agents, skills, MCP)
```

Full tree + rationale lives in the [bible](./weftlyinfo.md).

---

## 📚 Documentation

| Resource | Where |
|---|---|
| Design & roadmap | [`weftlyinfo.md`](./weftlyinfo.md) |
| Operator guide | `make docs-serve` then http://localhost:8000 |
| UI walkthrough | [`docs/guide/ui-walkthrough.md`](./docs/guide/ui-walkthrough.md) |
| Run script | [`RUN.md`](./RUN.md) |
| Architecture deep-dive | [`docs/architecture.md`](./docs/architecture.md) |

---

## 🧪 Testing

| Tier | Marker | What it covers |
|---|---|---|
| **Unit** | `unit` | Pure functions, domain types, mappers — no IO. |
| **Integration** | `integration` | API + DB + engine wired up; uses sqlite/postgres. |
| **Node** | `node` | Per-node contract tests (one behaviour per test, AAA). |
| **Live** | `live` | Hits real third-party APIs. Opt-in via env. |
| **Load** | `load` | Throughput + latency budgets under concurrency. |

```bash
make test                  # default: unit + integration
pytest -m node             # node-level contracts
pytest -m "live"           # live integrations (requires creds)
```

---

## 🛡 Licensing & IP

Weftlyflow is **original code** released under the [Apache 2.0 License](./LICENSE).
It is **not** a fork of n8n.
See **§23 of the bible** for the clean-room rules every contribution must follow:

- ❌ No copied code
- ❌ No copied identifiers
- ❌ No copied node names or credential slugs
- ✅ Read for architecture, then close the file and write from scratch

---

## 🤝 Contributing

Every new node, credential type, or architectural change must preserve the conventions in **§22 of the bible**:

- **Strict typing** — `mypy --strict` must pass; no bare `Any`.
- **Google-style docstrings** on every public class/function.
- **AAA tests** (arrange-act-assert), one behaviour per test.
- **Layer boundaries** — `server / worker / webhooks / triggers → engine → nodes / credentials / expression → domain`.
- **No `print()`** in library code — use `structlog.get_logger(__name__)`.
- **No file > 400 lines** without refactoring.

Run the local CI gate before opening a PR:

```bash
make lint && make typecheck && make test
```

---

<div align="center">

**Weftlyflow** — built for self-hosters who want n8n-class workflow power, in Python, on their own metal.

[⬆ Back to top](#weftlyflow)

</div>
