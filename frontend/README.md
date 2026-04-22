# Weftlyflow frontend

Vue 3 + Vite + TypeScript SPA. See the parent `RUN.md` for the full
validation block; quick start below.

## One-time setup

```bash
cd frontend
npm install
npx playwright install --with-deps chromium   # only needed for `npm run e2e`
```

## Dev

```bash
# In terminal A — backend (env vars pin the bootstrap admin).
WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL=admin@weftlyflow.io \
WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD=s3cret \
make dev-api        # from the repo root

# In terminal B — Vite dev server (proxies /api, /oauth2, /webhook).
cd frontend
npm run dev         # → http://localhost:5173
```

Open http://localhost:5173, sign in as `admin@weftlyflow.io` / `s3cret`.

## Gate

```bash
npm run typecheck   # vue-tsc --noEmit
npm run lint        # eslint
npm run test        # vitest — unit smoke
npm run build       # production bundle → dist/
npm run e2e         # playwright — golden-path through the full stack
```

The E2E test spins up Vite itself via `webServer`; it still expects a
backend running on `:5678` and will log in with
`WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` (defaults match the Run
block in `RUN.md`).
