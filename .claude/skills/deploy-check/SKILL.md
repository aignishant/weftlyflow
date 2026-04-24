---
name: deploy-check
description: Pre-deploy gate for Weftlyflow. Manual invocation only. Runs lint, typecheck, tests, coverage, docs-build, security scan. Blocks on any red.
disable-model-invocation: true
allowed-tools: Read, Glob, Bash(make lint), Bash(make typecheck), Bash(make test-all), Bash(make coverage), Bash(make docs-build), Bash(git status:*), Bash(git log:*)
---

# Skill: deploy-check

## When

Before cutting a release, merging a release branch to `main`, or running `docker-compose` against production.

## Checklist (all must pass)

1. **Clean tree** — `git status --porcelain` is empty.
2. **Lint** — `make lint`.
3. **Type** — `make typecheck`.
4. **Tests** — `make test-all`.
5. **Coverage** — `make coverage` ≥ 80% overall (≥ 90% for `domain` + `engine`).
6. **Docs** — `make docs-build` with `--strict` (no broken links, no missing API pages).
7. **Security** — `pip-audit` clean; `bandit -r src/weftlyflow` clean.
8. **Migrations** — every pending migration applied on SQLite + Postgres test databases.
9. **Spec check** — `weftlyinfo.md §27` revision log has an entry for this release.
10. **Changelog** — `docs/changelog.md` updated.

## Output

```
# /deploy-check — <PASS|FAIL>

1. ✅ Clean tree
2. ✅ Lint
3. ✅ Type
4. ❌ Tests — 3 failures in tests/nodes/stripe
5. ⏭ Coverage — skipped (tests failed)
...

## Next actions
- ...
```
