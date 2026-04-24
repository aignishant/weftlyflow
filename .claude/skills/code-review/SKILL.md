---
name: code-review
description: Quick review of the current staged diff. Auto-invokes when the user says "review", "is this ready", "check my code". Delegates to the code-reviewer agent if the diff is large or security-sensitive.
allowed-tools: Read, Grep, Glob, Bash(git diff:*), Bash(git log:*), Bash(git status:*), Bash(make lint), Bash(make typecheck)
---

# Skill: code-review

## Pipeline

1. `git diff --staged --stat` — if > 15 files OR touches `src/weftlyflow/credentials/`, `auth/`, or `expression/`, delegate to the `code-reviewer` agent and stop.
2. Otherwise read the diff, run `make lint` + `make typecheck`.
3. Produce a short review grouped by severity (🔴 blocker, 🟡 major, 🔵 minor).

## Checks (fast path)

- Missing module docstring.
- Missing Google-style docstring on public class/function.
- `print(...)` instead of `structlog`.
- Layer violation: `src/weftlyflow/domain/**` importing from another Weftlyflow subpackage.
- File > 400 lines.
- New public identifier with unclear provenance (delegate to `ip-checker`).

## Output

```
## code-review

**Staged**: <N files, +A/-B lines>

🔴 <count>  🟡 <count>  🔵 <count>

- 🔴 `path:line` — <problem> — <fix>
- 🟡 `path:line` — <problem> — <fix>
...

✅ `make lint` passed   ✅ `make typecheck` passed
```
