---
description: Draft a Conventional Commits message for the staged diff.
---

# /git:commit

Draft a Conventional Commits message for the currently staged changes. Do NOT run `git commit` — only produce the message; the user decides when to commit.

## Rules

- Format: `<type>(<scope>): <summary>` — scope optional.
- Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`, `style`.
- Summary ≤ 72 chars, imperative mood.
- Body: bullet list of meaningful changes (the *why*, not the *what*).
- Footer: `BREAKING CHANGE:` if applicable, `Refs:` for tracker IDs.

## Workflow

1. `git status --porcelain` — list staged files.
2. `git diff --staged` — read the actual changes.
3. Classify: is this a feature, fix, refactor, test, or docs?
4. Draft. Show the message in a fenced block. Stop.
