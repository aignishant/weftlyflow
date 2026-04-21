# Agents

9 Weftlyflow-specific subagents. Invoke with `/agents` or let them auto-invoke on matching triggers.

| Agent | Model | Color | When it fires |
|---|---|---|---|
| **code-reviewer** | Sonnet | blue | "review", "check my code", "ready to commit", staged-diff reviews |
| **debugger** | Sonnet | red | Tracebacks, failing tests, "why is this broken" |
| **python-expert** | Sonnet | green | "make this pythonic", "fix typing", "convert to async" |
| **node-author** | Sonnet | teal | "add a node", "new integration", "scaffold a node" |
| **ip-checker** | Opus | yellow | Before merge, when adding code in `src/weftlyflow/nodes/` or `src/weftlyflow/credentials/types/` |
| **test-generator** | Sonnet | cyan | "write tests", "cover this", coverage gaps |
| **security-auditor** | Opus | red | Before release, "audit", "is this safe" |
| **devops-engineer** | Sonnet | orange | Dockerfile, CI, "deploy", compose changes |
| **refactor-specialist** | Sonnet | purple | "refactor", "split module", cross-file renames |

Each runs in an isolated context. They can read the repo and cite line numbers but only `code-reviewer` has direct Bash access for running lint/typecheck/tests.
