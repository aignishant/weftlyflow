---
name: scaffold-node
description: Generate a new Weftlyflow node package. Manual invocation only. Delegates to the node-author agent, then runs the ip-checker agent on the result before handing off to the user.
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash(make lint), Bash(make typecheck), Bash(python -m pytest:*)
---

# Skill: scaffold-node

## Usage

`/scaffold-node <slug> <display-name> <tier>`

- `slug` — lowercase snake_case, e.g. `stripe`, `google_sheets`.
- `display-name` — human label, e.g. "Stripe", "Google Sheets".
- `tier` — `core` | `integrations` | `ai`.

## Pipeline

1. **Dispatch** to the `node-author` agent with the arguments. It produces the node package, spec, tests, icon placeholder, and README.
2. **Dispatch** to the `ip-checker` agent to scan the produced files.
3. If the IP check blocks → surface the blockers, don't write to disk.
4. If the IP check is green → write files, run `make lint && make typecheck && pytest tests/nodes/<slug> -x`, report.

## Reminders surfaced to the user

- SVG icon must be sourced from Lucide / Simple Icons / our own — never lifted from n8n.
- Module docstring must cite the provider's **official** API docs (not n8n's integration page).
- Test fixtures must be handcrafted or from the provider's docs, never copied.
