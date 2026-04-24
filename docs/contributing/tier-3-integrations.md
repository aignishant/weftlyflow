# Tier-3 integrations (community track)

The core team ships ~90 built-in nodes across tiers 1 and 2 —
HTTP/REST, OAuth, signing, messaging, storage, and the core
databases. The **tier-3** catalogue (~240 long-tail integrations —
niche SaaS, vertical-specific APIs, geographical CRMs) is explicitly
**community-driven**.

This page is the handshake between someone who wants to add a tier-3
node and the maintainers reviewing it.

## Before you start

1. **Does a node already exist?** Check `src/weftlyflow/nodes/` and
   the [Built-in nodes](../nodes/index.md) index.
2. **Can the HTTP Request node do it?** For one-off workflows, yes.
   A dedicated node is worth the effort when the integration is
   used often enough that the user-facing UX gain (typed properties,
   credential auto-config, paginated iteration) pays for the
   maintenance cost.
3. **Does the provider have a stable, documented API?** Tier-3 nodes
   wrap **officially documented** endpoints. Reverse-engineered /
   undocumented APIs are not accepted — they break without warning
   and become a support burden.
4. **Is the provider's licence compatible?** You will be reading
   their docs; the node you write must be original code. See
   [IP compliance](ip-compliance.md) — the hard rule.

## Claiming a slot (no-dupe-work protocol)

Open a "Tier-3 intent" issue *before* you start coding. Title format:

```
tier-3: <provider-slug>
```

Body minimum:
- Provider homepage + link to the official API reference.
- Rough scope: which operations / resources the node will cover in
  v1 of the node, and which you're explicitly deferring.
- Your expected cadence (weekends / full-time / "it's done already").

A maintainer replies within a week either claiming the slot for you
or pointing you at an existing PR. Multiple contributors can work on
the same provider (Stripe is large enough for three nodes), but
each node should have one owner for that node's slug.

## Publish in-tree vs third-party

Two paths are supported.

### In-tree (built-in)

`src/weftlyflow/nodes/integrations/<slug>/`. The node ships with
the main wheel and gets listed in the built-in catalogue. Best for
widely-used providers; comes with a higher review bar.

Review bar:
- Happy-path + error-path + pagination tests, all `respx`-mocked.
- ≥ 80% unit-test line coverage *for the node's own module*.
- Idempotent `setup()` / `teardown()` if the node holds connection
  state.
- Credential type registered in `src/weftlyflow/credentials/types/`
  when the node needs auth the core doesn't already cover.
- Docstrings pass the project's Google-style convention
  (`ruff check --select D`).

### Third-party (entry-point)

The `pyproject.toml` exposes `[project.entry-points."weftlyflow.nodes"]`.
Any installable Python package can register nodes here:

```toml
# your-package/pyproject.toml
[project.entry-points."weftlyflow.nodes"]
acme_widget_send = "weftlyflow_acme.nodes.widget_send:WidgetSendNode"
acme_widget_list = "weftlyflow_acme.nodes.widget_list:WidgetListNode"
```

On startup, Weftlyflow's `NodeRegistry` discovers every entry point
registered against that group and loads the class. Third-party nodes
**must not** use the `weftlyflow.*` namespace prefix for their own
slugs — pick a vendor-scoped prefix (`acme.widget_send`) to avoid
colliding with built-ins.

Benefits of the third-party path:
- Release on your own cadence.
- Lighter review — just IP-compliance and a working entry-point
  registration; no enforced test coverage.
- Can depend on provider SDKs the core project doesn't want to
  pull in.

When a third-party node becomes sufficiently popular, the community
track can absorb it in-tree via a maintainer-led port — contact us
in an issue before donating code, so we can run IP-compliance checks
and restructure the slugs.

## Acceptance checklist (in-tree)

The reviewer will run through this list; you can save a round-trip
by self-checking:

- [ ] Issue claimed (see "Claiming a slot" above).
- [ ] Provider's official API docs cited in the node's module
      docstring. No third-party tutorial / Medium-post citations.
- [ ] No identifiers, parameter names, or descriptions copied from
      any other workflow-automation tool's equivalent node. Write
      from your own reading of the provider's docs.
- [ ] Icon is either from Simple Icons (attributed in the node's
      `README.md`), Lucide, or hand-drawn. Never scraped from the
      provider's website.
- [ ] Credential type chosen correctly — reuse
      `bearer_token` / `api_key_header` / `oauth2_generic` when
      possible. Add a custom type only when the provider's auth
      flow is genuinely novel.
- [ ] Tests cover: happy path, 4xx error (mapped to a clean
      `NodeExecutionError`), 5xx retry, pagination if the API
      paginates, and at least one property-validation case.
- [ ] `make lint && make typecheck && make test-node` all green
      locally before opening the PR.
- [ ] PR description links to the provider's API reference and
      names every operation the node supports.

## Support expectations

Tier-3 nodes are community-maintained. When the provider changes
their API, the node's **original author** is pinged first. If no
response within two weeks, the maintainers will either fix forward
(small changes) or deprecate the node with a release-note warning
(breaking changes that need re-design).

Opening an issue for a tier-3 node you did not author is fine —
just do not expect same-week turnaround. A tested patch always
moves faster than a bug report.
