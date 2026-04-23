# Multi-tenancy

Weftlyflow's tenant model is deliberately flat and explicit: **the project
is the tenancy boundary**. Every workflow, credential, execution, webhook,
and schedule belongs to exactly one project. The repository layer
auto-filters every query by `project_id`, so cross-project leakage is
structurally impossible — a bug in a route handler cannot accidentally
surface one tenant's workflows to another.

This guide covers:

- [The three-layer model](#the-three-layer-model) — users, projects, resources
- [Roles and permissions](#roles-and-permissions)
- [First-boot bootstrap](#first-boot-bootstrap)
- [How isolation is enforced](#how-isolation-is-enforced)
- [Current limits](#current-limits)

## The three-layer model

```
users ─── (owner_id) ───▶ projects ─── (project_id) ───▶ workflows, credentials, …
   │
   └── (default_project_id) ──▶ projects    (for UI session routing)
```

| Entity       | Cardinality                             | Purpose                                           |
| ------------ | --------------------------------------- | ------------------------------------------------- |
| User         | 1:1 with a real human or service account | Authentication subject, RBAC principal           |
| Project      | 1:many — each user owns at least one    | Tenant boundary; every resource hangs off it     |
| Workflow     | 1:many per project                       | Belongs to exactly one project                   |
| Credential   | 1:many per project                       | Belongs to exactly one project                   |

Every user gets a **personal project** at account creation. Additional
projects can be created through the API; the creator becomes the owner.

## Roles and permissions

Two orthogonal RBAC axes ship today:

### Global role — stored on `users.global_role`

| Role     | Grants                                                                                  |
| -------- | --------------------------------------------------------------------------------------- |
| `owner`  | Bypasses the per-project `owner_id` check in `get_current_project` — can access every project. Reserved for operator-style accounts. |
| `admin`  | Reserved for user administration (create / disable users). No cross-project data access until the project-member model lands. |
| `member` | Default. Access only to projects the user owns (or — in future — is a member of).       |

First-boot admins get `owner`. SSO-provisioned users get `member`.
Changes happen through the admin routes and are audited.

### Project kind — stored on `projects.kind`

| Kind       | Meaning                                                                                |
| ---------- | -------------------------------------------------------------------------------------- |
| `personal` | Auto-created alongside a user. Not intended for sharing.                               |
| `team`     | Operator-created project for shared work. Same isolation semantics, different default discoverability. |

The kind does not change isolation behaviour — both kinds are scoped
the same way by the repository layer. It's a UI hint and an audit
convenience.

## First-boot bootstrap

The API lifespan invokes `ensure_bootstrap_admin` exactly once per empty
database. Behaviour:

| Environment | `WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL` / `…_PASSWORD` | Behaviour                                                               |
| ----------- | ------------------------------------------------- | ----------------------------------------------------------------------- |
| Any         | Both set                                           | Create that user as `owner` + a personal project; log the email.         |
| `development` | Unset                                             | Generate a random password, log it at warning level, use `admin@weftlyflow.io`. |
| `production`  | Unset                                             | **Refuse to start** — `BootstrapError`.                                  |

The production refusal is intentional: a silently auto-generated
production admin is a foot-gun that has lost credentials for more than
one operator. Set both env vars, or don't boot.

## How isolation is enforced

### Repository-layer auto-scoping

Every `*Repository` method accepts `project_id` as a required kwarg and
emits `WHERE project_id = :project_id` in the generated SQL. There is no
"get by id" shortcut that skips the scope — look at
`src/weftlyflow/db/repositories/workflow_repo.py:get()` for the
canonical shape.

### Route-layer dependency injection

FastAPI's dependency system resolves the caller's project through
`get_current_project` (`src/weftlyflow/server/deps.py`). It checks the
`X-Weftlyflow-Project` request header first — so a user who owns
multiple projects can switch context without re-logging in — and falls
back to the user's `default_project_id`. Access is granted only when the
project's `owner_id` matches the caller, or the caller's global role is
`owner`. A handler must take
`project_id: str = Depends(get_current_project)` to see the value —
there is no ambient state.

### Execution context

Workflow execution receives the `project_id` through
`ExecutionContext.project_id`. Nodes that load credentials do so through
`ctx.load_credential(slot)`, which is itself scoped — a workflow in one
project cannot reference a credential in another even if it guesses the
credential id.

### Audit trail

Every state-mutating operation writes an `audit_event` row tagged with
the acting `user_id` and the affected `project_id`, retained for
`audit_retention_days` (default 90).

## Current limits

Ship vs. roadmap, so operators can plan around the gap:

- **No cross-user project sharing yet.** A user can own multiple
  projects but cannot grant another user access to a project they own.
  Today, sharing work across teammates requires either putting every
  teammate on a shared set of credentials or exporting + importing
  workflows. The project-member model (with per-project roles
  `viewer`, `editor`, `admin`) is planned; the entity stub exists but
  the routes and repository methods are not yet shipped.
- **No per-resource ACLs.** Visibility is project-scoped, period.
  "Team Alice can see workflow X but not credential Y in the same
  project" is not expressible.
- **No per-project quotas.** There is no built-in ceiling on the
  number of workflows, executions, or webhooks per project. Operators
  running shared infrastructure should enforce quotas out-of-band
  (e.g., a reverse-proxy rate limit on `/api/v1/executions`).

If any of these matter for your deployment, pin to the
[changelog](../changelog.md) — the project-member model is expected to
land in a near-term tranche.
