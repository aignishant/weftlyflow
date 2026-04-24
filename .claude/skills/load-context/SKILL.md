---
name: load-context
description: Orient a fresh Claude Code session on Weftlyflow. Manual invocation. Reads the bible, the current memory index, and git state; returns a concise situational summary.
disable-model-invocation: true
allowed-tools: Read, Glob, Bash(git status:*), Bash(git log:*), Bash(git branch:*)
---

# Skill: load-context

Produce a ≤ 250-word brief for the current session:

1. **Project** — "Weftlyflow, Python replica of n8n, pre-alpha, Phase X."
2. **Working state** — branch, HEAD, dirty-file count.
3. **Where we are in the roadmap** — reference `weftlyinfo.md §24`; which phase's deliverables are complete / pending.
4. **Memory highlights** — skim the MEMORY.md index; list open feedback rules and any phase-specific project memory.
5. **Next natural step** — one sentence: "the next unchecked item in Phase X is Y, start with `file:line`".

Do not run commands other than git metadata reads. Do not modify files.
