# 03 — Skills, agents, hooks

## Skills vs agents vs commands

| Thing | Lives in | Invocation | Context |
|---|---|---|---|
| **Skill** | `.claude/skills/<name>/SKILL.md` | auto + `/<name>` | same session (or forked if `context: fork`) |
| **Agent** | `.claude/agents/<name>.md` | `/agents` or auto-trigger from description | **isolated** — no prior convo access |
| **Command** | `.claude/commands/<name>.md` | `/<name>` | same session |

Pick a skill when the workflow is self-contained and benefits from auto-invocation. Pick an agent when you need a fresh context (review, audit, research). Commands are legacy — prefer skills.

## How Weftlyflow's fit together

- `/code-review` (skill) does the fast path; delegates to `code-reviewer` (agent) for big diffs.
- `/scaffold-node` (skill) chains `node-author` (agent) → `ip-checker` (agent) → writes files.
- `debugger` (agent) is triggered by `/python-testing` (skill) when tests fail.

## Hooks

Event-driven automation declared in `.claude/hooks/hooks.json`. See `.claude/hooks/README.md`. Changes to hook files require a Claude Code restart.
