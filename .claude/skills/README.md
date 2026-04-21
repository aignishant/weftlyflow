# Skills

On-demand and auto-triggered workflows for Weftlyflow.

| Skill | Trigger | Purpose |
|---|---|---|
| **python-testing** | auto + `/python-testing` | Run pytest with the right markers; interpret failures. |
| **code-review** | auto + `/code-review` | Quick review of staged diff; delegates to `code-reviewer` agent for big diffs. |
| **scaffold-node** | `/scaffold-node <slug>` | Generate a new node package with tests + docs stub via the `node-author` agent. |
| **deploy-check** | `/deploy-check` | Pre-deploy gate: lint, typecheck, tests, coverage, docs, security. |
| **release-notes** | `/release-notes <tag-range>` | Draft changelog from commits between tags. |
| **load-context** | `/load-context` | Orient a fresh session on Weftlyflow state (architecture, layer rules). |
